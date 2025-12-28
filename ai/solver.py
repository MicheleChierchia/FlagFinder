import random
import sys
import os
import csv

# Setup path come richiesto
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, 'game'))

import tkinter as tk
from game.minesweeper import MinesweeperGUI

class MinesweeperAI:
    def __init__(self, game_logic):
        self.game = game_logic
        self.running = False
        
        # Nome del file per il dataset
        self.csv_filename = 'minesweeper_dataset.csv'
        
        # Inizializza il CSV con header se non esiste
        if not os.path.exists(self.csv_filename):
            try:
                with open(self.csv_filename, mode='w', newline='') as f:
                    writer = csv.writer(f)
                    # 8 Features (Vicini) + 1 Target (safe)
                    # Ordine: TopLeft, Top, TopRight, Left, Right, BottomLeft, Bottom, BottomRight, safe
                    header = ['TL', 'T', 'TR', 'L', 'R', 'BL', 'B', 'BR', 'safe']
                    writer.writerow(header)
            except IOError as e:
                print(f"Errore inizializzazione CSV: {e}")

    def step(self):
        """
        Esegue un passo dell'AI. Ritorna True se è stata fatta una mossa.
        """
        if self.game.game_over:
            return False

        made_move = False
        
        # --- 1. Logica Deterministica (Constraint Satisfaction) ---
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                if self.game.game_over: return False

                cell = self.game.board[r][c]
                
                if cell.is_revealed and cell.adjacent_mines > 0:
                    neighbors_coords = self.game.get_neighbors(r, c)
                    neighbors = [self.game.board[nr][nc] for nr, nc in neighbors_coords]
                    
                    hidden_coords = [(n.r, n.c) for n in neighbors if not n.is_revealed and not n.is_flagged]
                    flagged_count = len([n for n in neighbors if n.is_flagged])
                    
                    if not hidden_coords:
                        continue
                        
                    # Regola: Value == Flags + Hidden -> Tutto il resto è mina
                    if cell.adjacent_mines == flagged_count + len(hidden_coords):
                        for (hr, hc) in hidden_coords:
                            self.game.toggle_flag(hr, hc)
                            made_move = True
                            
                    # Regola: Value == Flags -> Tutto il resto è sicuro
                    elif cell.adjacent_mines == flagged_count:
                        for (hr, hc) in hidden_coords:
                            self.game.reveal(hr, hc)
                            made_move = True

        if made_move:
            return True

        # --- 2. Logica Avanzata (Insiemi) ---
        if self.run_advanced_logic():
             return True

        # --- 3. Guessing (con Data Logging) ---
        # Se siamo qui, l'AI è bloccata e deve tirare a indovinare.
        self.make_guess()
        return True

    def run_advanced_logic(self):
        active_cells = []
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                cell = self.game.board[r][c]
                if cell.is_revealed and cell.adjacent_mines > 0:
                     neighbors_coords = self.game.get_neighbors(r, c)
                     hidden = [(nr, nc) for nr, nc in neighbors_coords 
                               if not self.game.board[nr][nc].is_revealed 
                               and not self.game.board[nr][nc].is_flagged]
                     
                     if hidden:
                         flagged_count = len([n for n in neighbors_coords if self.game.board[n[0]][n[1]].is_flagged])
                         remaining_mines = cell.adjacent_mines - flagged_count
                         active_cells.append({
                             'pos': (r, c),
                             'hidden': set(hidden),
                             'remaining_mines': remaining_mines
                         })
        
        made_move = False
        
        for i in range(len(active_cells)):
            for j in range(len(active_cells)):
                if i == j: continue
                
                A = active_cells[i]
                B = active_cells[j]
                
                if A['hidden'].issubset(B['hidden']):
                    diff_set = B['hidden'] - A['hidden']
                    if not diff_set: continue
                        
                    mine_diff = B['remaining_mines'] - A['remaining_mines']
                    
                    if mine_diff == 0:
                        for (dr, dc) in diff_set:
                            self.game.reveal(dr, dc)
                            made_move = True
                    elif mine_diff == len(diff_set):
                        for (dr, dc) in diff_set:
                            self.game.toggle_flag(dr, dc)
                            made_move = True
        return made_move

    def _record_guess_data(self, r, c, is_safe):
        """
        Metodo privato per salvare lo snapshot della board attorno a (r, c)
        e l'etichetta di verità (safe).
        """
        data_row = []
        
        # Offset in senso orario da Top-Left a Bottom-Right
        offsets = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1)
        ]
        
        for dr, dc in offsets:
            nr, nc = r + dr, c + dc
            
            # --- Encoding ---
            # -2: Muro / Fuori mappa
            if not (0 <= nr < self.game.rows and 0 <= nc < self.game.cols):
                data_row.append(-2)
            else:
                cell = self.game.board[nr][nc]
                # -1: Cella non rivelata (o flaggata, per l'AI è "coperta")
                if not cell.is_revealed:
                    data_row.append(-1)
                else:
                    # 0-8: Valore numerico visibile
                    data_row.append(cell.adjacent_mines)
        
        # Aggiungi Label (Target)
        # 1 = SAFE, 0 = NOT SAFE (MINE)
        data_row.append(1 if is_safe else 0)
        
        # Scrittura su file
        try:
            with open(self.csv_filename, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(data_row)
        except Exception as e:
            print(f"Errore durante il salvataggio dati: {e}")

    def make_guess(self):
        """
        Sceglie una mossa probabilistica, registra i dati per il dataset,
        ed esegue la mossa.
        """
        # 1. Identifica le celle candidabili (Frontiera)
        frontier = set()
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                if self.game.board[r][c].is_revealed:
                    for nr, nc in self.game.get_neighbors(r, c):
                        if not self.game.board[nr][nc].is_revealed and not self.game.board[nr][nc].is_flagged:
                            frontier.add((nr, nc))
        
        if frontier:
            gr, gc = random.choice(list(frontier))
        else:
            # Fallback: cella casuale non rivelata (es. inizio partita)
            hidden_cells = []
            for r in range(self.game.rows):
                for c in range(self.game.cols):
                    if not self.game.board[r][c].is_revealed and not self.game.board[r][c].is_flagged:
                        hidden_cells.append((r, c))
            if not hidden_cells: return
            gr, gc = random.choice(hidden_cells)
            
        # 2. Determina la Ground Truth (Sbirciatina per il dataset)
        is_actually_safe = not self.game.board[gr][gc].is_mine

        # 3. Registra i dati (Features + Target 'safe')
        self._record_guess_data(gr, gc, is_actually_safe)

        # 4. Esegui la mossa nel gioco
        self.game.reveal(gr, gc)

    def run_gui_loop(self, root, gui_update_callback):
        if not self.running:
            center_r, center_c = self.game.rows // 2, self.game.cols // 2
            self.game.reveal(center_r, center_c)
            self.running = True
            gui_update_callback()
        
        if self.game.game_over:
            print("AI: Partita terminata.")
            return

        self.step()
        gui_update_callback()
        
        root.after(100, lambda: self.run_gui_loop(root, gui_update_callback))

if __name__ == "__main__":
    root = tk.Tk()
    app = MinesweeperGUI(root)
    
    ai = MinesweeperAI(app.game)
    
    root.after(1, lambda: ai.run_gui_loop(root, app.update_gui))
    
    root.mainloop()