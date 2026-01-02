import random
import sys
import os
import tkinter as tk
import warnings
import pandas as pd 
import joblib
import csv 

# Cache globale per il modello
_CACHED_MODEL = None
_MODEL_ATTEMPTED = False

CSV_FILE = 'minesweeper_dataset.csv'

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.minesweeper import MinesweeperGUI

class MinesweeperAI:
    def __init__(self, game_logic):
        self.game = game_logic
        self.running = False
        
        # --- TRACKING INTERNO ---
        # Teniamo il conto noi per evitare cicli inutili
        self.flags_count = 0 
        
        # --- DEFINIZIONE FEATURE ---
        self.grid_features = [f"cell_{r}_{c}" for r in range(-2, 3) for c in range(-2, 3) if not (r==0 and c==0)]
        self.meta_features = ['global_density'] 
        self.dataset_columns = self.grid_features + self.meta_features
        
        # --- CARICAMENTO MODELLO ML ---
        global _CACHED_MODEL, _MODEL_ATTEMPTED
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'minesweeper_ai_model.pkl')
        
        if not _MODEL_ATTEMPTED:
            _MODEL_ATTEMPTED = True
            if os.path.exists(model_path):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        loaded_model = joblib.load(model_path)
                    if hasattr(loaded_model, "verbose"):
                        loaded_model.verbose = 0
                    _CACHED_MODEL = loaded_model
                    print("AI: Modello ML caricato.")
                except Exception as e:
                    print(f"AI: Errore caricamento modello: {e}")
        self.model = _CACHED_MODEL

    def _place_flag(self, r, c):
        """Wrapper per piazzare bandiere e aggiornare il conteggio."""
        if not self.game.board[r][c].is_flagged:
            self.game.toggle_flag(r, c)
            self.flags_count += 1

    def _get_effective_value(self, r, c):
        if not (0 <= r < self.game.rows and 0 <= c < self.game.cols): return -2
        cell = self.game.board[r][c]
        if not cell.is_revealed: return -1

        neighbors = self.game.get_neighbors(r, c)
        # Qui usiamo ancora un mini-ciclo locale perché i vicini sono solo max 8 (trascurabile)
        current_flags = len([n for n in neighbors if self.game.board[n[0]][n[1]].is_flagged])
        return cell.adjacent_mines - current_flags

    def _get_features_for_cell(self, r, c):
        features = []
        
        # A. Feature Locali
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if dr == 0 and dc == 0: continue
                val = self._get_effective_value(r + dr, c + dc)
                features.append(val)
        
        # B. Feature Globale: Global Density
        # Mine rimaste (basato sul nostro contatore veloce)
        mines_left = self.game.mines - self.flags_count
        
        # Celle rivelate (Dobbiamo contarle per forza a causa del Flood Fill, ma usiamo sum veloce)
        # Se modifichi game_logic per avere self.game.revealed_count, usa quello!
        total_cells = self.game.rows * self.game.cols
        revealed_count = sum(cell.is_revealed for row in self.game.board for cell in row)
        
        hidden_cells = total_cells - revealed_count
        
        if hidden_cells > 0:
            density = mines_left / hidden_cells
        else:
            density = 0.0
            
        features.append(density)
        return features

    def _save_dataset(self, features, label):
        try:
            file_exists = os.path.isfile(CSV_FILE)
            with open(CSV_FILE, mode='a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(self.dataset_columns + ['safe'])
                writer.writerow(features + [label])
        except Exception:
            pass

    def step(self):
        if self.game.game_over: return False
        made_move = False
        
        # 1. Logica Base
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                if self.game.game_over: return False
                cell = self.game.board[r][c]
                
                if cell.is_revealed and cell.adjacent_mines > 0:
                    neighbors = [self.game.board[nr][nc] for nr, nc in self.game.get_neighbors(r, c)]
                    hidden = [(n.r, n.c) for n in neighbors if not n.is_revealed and not n.is_flagged]
                    flags = len([n for n in neighbors if n.is_flagged])
                    
                    if not hidden: continue
                        
                    if len(hidden) == cell.adjacent_mines - flags:
                        for hr, hc in hidden:
                            self._place_flag(hr, hc) # Usa il wrapper!
                            made_move = True
                            
                    elif cell.adjacent_mines == flags:
                        for hr, hc in hidden:
                            self.game.reveal(hr, hc)
                            made_move = True

        if made_move: return True

        # 2. Logica Avanzata
        if self.run_advanced_logic(): return True

        # 3. Guessing (ML o Random)
        self.make_guess_with_ml()
        return True

    def run_advanced_logic(self):
        active_cells = []
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                cell = self.game.board[r][c]
                if cell.is_revealed and cell.adjacent_mines > 0:
                     neighbors = self.game.get_neighbors(r, c)
                     hidden = [(nr, nc) for nr, nc in neighbors 
                               if not self.game.board[nr][nc].is_revealed 
                               and not self.game.board[nr][nc].is_flagged]
                     if hidden:
                         flags = len([n for n in neighbors if self.game.board[n[0]][n[1]].is_flagged])
                         active_cells.append({
                             'hidden': set(hidden),
                             'remaining': cell.adjacent_mines - flags
                         })
        
        made_move = False
        for i in range(len(active_cells)):
            for j in range(len(active_cells)):
                if i == j: continue
                A, B = active_cells[i], active_cells[j]
                
                if A['hidden'].issubset(B['hidden']):
                    diff = B['hidden'] - A['hidden']
                    if not diff: continue
                    mine_diff = B['remaining'] - A['remaining']
                    
                    if mine_diff == 0:
                        for dr, dc in diff:
                            self.game.reveal(dr, dc)
                            made_move = True
                    elif mine_diff == len(diff):
                        for dr, dc in diff:
                            self._place_flag(dr, dc) # Usa il wrapper!
                            made_move = True
        return made_move

    def make_guess_with_ml(self):
        frontier = set()
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                if self.game.board[r][c].is_revealed:
                    for nr, nc in self.game.get_neighbors(r, c):
                        if not self.game.board[nr][nc].is_revealed and not self.game.board[nr][nc].is_flagged:
                            frontier.add((nr, nc))
        
        frontier_list = list(frontier)
        
        if not frontier_list:
            hidden = []
            for r in range(self.game.rows):
                for c in range(self.game.cols):
                    if not self.game.board[r][c].is_revealed and not self.game.board[r][c].is_flagged:
                        hidden.append((r, c))
            if not hidden: return
            frontier_list = hidden

        best_move = None
        
        # --- PREDIZIONE ---
        if self.model:
            features_batch = []
            for r, c in frontier_list:
                features_batch.append(self._get_features_for_cell(r, c))
            
            X_input = pd.DataFrame(features_batch, columns=self.dataset_columns)
            
            try:
                probs = self.model.predict_proba(X_input)
                safe_probs = probs[:, 1]
                best_idx = safe_probs.argmax()
                best_move = frontier_list[best_idx]
            except Exception:
                best_move = random.choice(frontier_list)
        else:
            best_move = random.choice(frontier_list)

        # --- ESECUZIONE ---
        if best_move:
            move_features = self._get_features_for_cell(best_move[0], best_move[1])
            self.game.reveal(best_move[0], best_move[1])
            label = 1 
            if self.game.game_over and not self.game.victory:
                label = 0 
            self._save_dataset(move_features, label)

    def run_gui_loop(self, root, gui_update_callback):
        if not self.running:
            cr, cc = self.game.rows // 2, self.game.cols // 2
            self.game.reveal(cr, cc)
            self.running = True
            gui_update_callback()
        
        if self.game.game_over:
            return

        self.step()
        gui_update_callback()
        root.after(100, lambda: self.run_gui_loop(root, gui_update_callback))

if __name__ == "__main__":
    root = tk.Tk()
    app = MinesweeperGUI(root,16,30,99)
    ai = MinesweeperAI(app.game)
    root.after(100, lambda: ai.run_gui_loop(root, app.update_gui))
    root.mainloop()