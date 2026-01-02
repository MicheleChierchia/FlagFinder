import random
import sys
import os
import joblib
import numpy as np
import tkinter as tk
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

# Configurazione Percorsi
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from game.minesweeper import MinesweeperGUI

# FILE DI MEMORIA (Vengono creati automaticamente)
MODEL_FILE = 'minesweeper_brain_online.pkl'
SCALER_FILE = 'minesweeper_scaler_online.pkl'

class MinesweeperAI:
    def __init__(self, game_logic, root_window):
        self.game = game_logic
        self.root = root_window  # Riferimento alla finestra per gestire i timer
        self.running = False
        
        # PARAMETRI APPRENDIMENTO
        self.epsilon = 0.3      # 30% probabilità iniziale di esplorazione
        self.epsilon_decay = 0.995 
        self.min_epsilon = 0.05
        
        # MEMORIA TEMPORANEA (Reset a ogni partita)
        self.game_memory = [] 
        
        # --- INIZIALIZZAZIONE CERVELLO ---
        self.model = None
        self.scaler = None
        self.is_fitted = False
        
        # Carica o Crea
        if os.path.exists(MODEL_FILE) and os.path.exists(SCALER_FILE):
            try:
                self.model = joblib.load(MODEL_FILE)
                self.scaler = joblib.load(SCALER_FILE)
                self.is_fitted = True
                print(">> Cervello caricato. Continuo l'addestramento...")
            except:
                print(">> File corrotti. Creo nuovo cervello.")
                self._create_new_brain()
        else:
            print(">> Nessun cervello trovato. Inizio da zero.")
            self._create_new_brain()

    def _create_new_brain(self):
        # Rete Neurale ottimizzata per apprendimento incrementale
        self.model = MLPClassifier(
            hidden_layer_sizes=(64, 32, 16),
            activation='relu',
            solver='adam',
            learning_rate='adaptive',
            learning_rate_init=0.001,
            random_state=42
        )
        self.scaler = StandardScaler()
        self.is_fitted = False

    # --- FEATURE EXTRACTION ---
    def _get_effective_value(self, r, c):
        if not (0 <= r < self.game.rows and 0 <= c < self.game.cols): return -2
        cell = self.game.board[r][c]
        if not cell.is_revealed: return -1
        neighbors = self.game.get_neighbors(r, c)
        current_flags = len([n for n in neighbors if self.game.board[n[0]][n[1]].is_flagged])
        return cell.adjacent_mines - current_flags

    def _get_features_for_cell(self, r, c):
        features = []
        # 24 celle vicine
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if dr == 0 and dc == 0: continue
                val = self._get_effective_value(r + dr, c + dc)
                features.append(val)
        
        # Feature Globale: Densità
        flags = sum(c.is_flagged for row in self.game.board for c in row)
        revealed = sum(c.is_revealed for row in self.game.board for c in row)
        total = self.game.rows * self.game.cols
        mines_left = self.game.mines - flags
        hidden = total - revealed
        density = (mines_left / hidden) if hidden > 0 else 0.0
        features.append(density)
        return features

    # --- LOOP LOGICO PRINCIPALE ---
    def step(self):
        # Se il gioco è finito, gestiamo l'apprendimento e ci fermiamo
        if self.game.game_over:
            self.learn_from_game(victory=False)
            return False
            
        # Controllo Vittoria Manuale
        revealed_count = sum(c.is_revealed for row in self.game.board for c in row)
        if revealed_count == (self.game.rows * self.game.cols) - self.game.mines:
            self.learn_from_game(victory=True)
            return False

        made_move = False
        
        # 1. Logica Deterministica (Base + Avanzata)
        if self.run_deterministic_logic(): 
            return True

        # 2. Smart Guessing (Apprendimento)
        self.make_smart_guess()
        return True

    def run_deterministic_logic(self):
        """Include sia la logica base che quella avanzata (insiemi)."""
        made_move = False
        
        # --- A. LOGICA BASE ---
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
                        for hr, hc in hidden: self.game.toggle_flag(hr, hc); made_move = True
                    elif cell.adjacent_mines == flags:
                        for hr, hc in hidden: self.game.reveal(hr, hc); made_move = True
        
        if made_move: return True

        # --- B. LOGICA AVANZATA (Insiemi) ---
        active_cells = []
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                cell = self.game.board[r][c]
                if cell.is_revealed and cell.adjacent_mines > 0:
                    neighbors = self.game.get_neighbors(r, c)
                    hidden = [(nr, nc) for nr, nc in neighbors if not self.game.board[nr][nc].is_revealed and not self.game.board[nr][nc].is_flagged]
                    if hidden:
                        flags = len([n for n in neighbors if self.game.board[n[0]][n[1]].is_flagged])
                        active_cells.append({'hidden': set(hidden), 'remaining': cell.adjacent_mines - flags})
        
        for i in range(len(active_cells)):
            for j in range(len(active_cells)):
                if i == j: continue
                A, B = active_cells[i], active_cells[j]
                if A['hidden'].issubset(B['hidden']):
                    diff = B['hidden'] - A['hidden']
                    if not diff: continue
                    mine_diff = B['remaining'] - A['remaining']
                    if mine_diff == 0:
                        for dr, dc in diff: self.game.reveal(dr, dc); made_move = True
                    elif mine_diff == len(diff):
                        for dr, dc in diff: self.game.toggle_flag(dr, dc); made_move = True
        
        return made_move

    def make_smart_guess(self):
        # Trova frontiera
        candidates = set()
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                if self.game.board[r][c].is_revealed:
                    for nr, nc in self.game.get_neighbors(r, c):
                        n = self.game.board[nr][nc]
                        if not n.is_revealed and not n.is_flagged: candidates.add((nr, nc))
        
        # Se vuoto (inizio gioco), prendi tutto
        if not candidates:
            for r in range(self.game.rows):
                for c in range(self.game.cols):
                    if not self.game.board[r][c].is_revealed and not self.game.board[r][c].is_flagged:
                        candidates.add((r, c))
        
        if not candidates: return

        candidates_list = list(candidates)
        
        # Decisione: Random (Esplora) vs AI (Sfrutta)
        use_random = (not self.is_fitted) or (random.random() < self.epsilon)
        
        if use_random:
            gr, gc = random.choice(candidates_list)
            feats = self._get_features_for_cell(gr, gc)
            # Salviamo in memoria
            self.game_memory.append({'features': feats, 'r': gr, 'c': gc})
            # print(f"Esplorazione (rnd): {gr, gc}")
            self.game.reveal(gr, gc)
        else:
            X_candidates = [self._get_features_for_cell(r, c) for r, c in candidates_list]
            X_scaled = self.scaler.transform(X_candidates)
            probs = self.model.predict_proba(X_scaled)[:, 1] # Probabilità Safe
            
            best_idx = np.argmax(probs)
            gr, gc = candidates_list[best_idx]
            
            self.game_memory.append({'features': X_candidates[best_idx], 'r': gr, 'c': gc})
            print(f"IA Guess ({probs[best_idx]*100:.1f}% safe): {gr, gc}")
            self.game.reveal(gr, gc)

    def learn_from_game(self, victory):
        """Impara dalla partita conclusa e pianifica il restart."""
        self.running = False # Ferma subito il loop grafico

        if not self.game_memory:
            self.trigger_auto_restart()
            return

        print(f"\n--- FINE PARTITA ({'VITTORIA' if victory else 'Sconfitta'}) ---")
        
        X_batch = []
        y_batch = []
        
        for move in self.game_memory:
            r, c = move['r'], move['c']
            cell = self.game.board[r][c]
            # Se è una mina (anche se l'abbiamo fatta esplodere noi), il label è 0 (Pericolo)
            label = 0 if cell.is_mine else 1
            X_batch.append(move['features'])
            y_batch.append(label)

        X_batch = np.array(X_batch)
        y_batch = np.array(y_batch)

        # Partial Fit
        self.scaler.partial_fit(X_batch)
        X_batch_scaled = self.scaler.transform(X_batch)
        self.model.partial_fit(X_batch_scaled, y_batch, classes=[0, 1])
        self.is_fitted = True
        
        # Salva
        joblib.dump(self.model, MODEL_FILE)
        joblib.dump(self.scaler, SCALER_FILE)
        
        print(f">> Cervello aggiornato con {len(X_batch)} esempi. Epsilon: {self.epsilon:.3f}")

        # Riduci Epsilon
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
        self.game_memory = [] # Pulisci memoria
        
        # AUTO RESTART SICURO
        self.trigger_auto_restart()

    def trigger_auto_restart(self):
        """Riavvia il gioco dopo 1 secondo per evitare crash di Tkinter."""
        print(">> Riavvio automatico tra 1 secondo...")
        self.root.after(1000, self.perform_reset)

    def perform_reset(self):
        """Esegue il reset effettivo."""
        self.game.reset()
        self.game_memory = []
        # Rilancia il loop grafico
        self.running = False
        self.run_gui_loop(self.root, lambda: None) # Lambda vuota perché update_gui è gestito dalla app principale solitamente

    def run_gui_loop(self, root, gui_update_callback):
        # Gestione primo avvio o restart
        if not self.running:
            if not self.game.game_over:
                # Start Safe
                cr, cc = self.game.rows // 2, self.game.cols // 2
                self.game.reveal(cr, cc)
                self.running = True
                if gui_update_callback: gui_update_callback()
        
        if self.game.game_over:
            # Se il gioco è finito, assicuriamoci che learn_from_game sia stato chiamato
            # step() se ne occupa, ma se siamo qui e running è ancora True, chiamiamolo.
            if self.running:
                self.step()
            return # Usciamo dal loop, ci penserà trigger_auto_restart a rientrare

        self.step()
        if gui_update_callback: gui_update_callback()
        
        if self.running:
            # Velocità loop (10ms = molto veloce)
            root.after(10, lambda: self.run_gui_loop(root, gui_update_callback))

if __name__ == "__main__":
    root = tk.Tk()
    app = MinesweeperGUI(root)
    
    # Passiamo 'root' all'IA per gestire i timer
    ai = MinesweeperAI(app.game, root)
    
    # Avvio ritardato
    root.after(500, lambda: ai.run_gui_loop(root, app.update_gui))
    root.mainloop()