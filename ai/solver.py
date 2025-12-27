import random
import sys
import os

# Permette import se eseguito come script
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
# Add game directory to sys.path to satisfy internal imports in minesweeper.py
sys.path.append(os.path.join(project_root, 'game'))

import tkinter as tk
from game.minesweeper import MinesweeperGUI

class MinesweeperAI:
    def __init__(self, game_logic):

        self.game = game_logic
        self.running = False

    def step(self):
        if self.game.game_over:
            return False

        made_move = False
        
        # 1. Basic Constraint Satisfaction (Hill Climbing)
        for r in range(self.game.rows):
            for c in range(self.game.cols):
                if self.game.game_over: return False

                cell = self.game.board[r][c]
                
                # Analizziamo solo celle rivelate con numeri
                if cell.is_revealed and cell.adjacent_mines > 0:
                    neighbors_coords = self.game.get_neighbors(r, c)
                    neighbors = [self.game.board[nr][nc] for nr, nc in neighbors_coords]
                    
                    hidden_coords = [(n.r, n.c) for n in neighbors if not n.is_revealed and not n.is_flagged]
                    flagged_count = len([n for n in neighbors if n.is_flagged])
                    
                    if not hidden_coords:
                        continue
                        
                    # Regola 1: Se value == flags + hidden, allora tutti gli hidden sono mine
                    if cell.adjacent_mines == flagged_count + len(hidden_coords):
                        for (hr, hc) in hidden_coords:
                            # print(f"AI: Flagging ({hr}, {hc})")
                            self.game.toggle_flag(hr, hc)
                            made_move = True
                            
                    # Regola 2: Se value == flags, allora tutti gli hidden sono sicuri
                    elif cell.adjacent_mines == flagged_count:
                        for (hr, hc) in hidden_coords:
                            # print(f"AI: Revealing ({hr}, {hc})")
                            self.game.reveal(hr, hc)
                            made_move = True

        if made_move:
            return True

        # 2. Advanced Logic (Set Difference)
        if self.run_advanced_logic():
             return True

        # 3. Guessing (se bloccato)
        # print("AI: Stuck with deterministic logic.")
        self.make_guess()
        return True

    def run_advanced_logic(self):
        # Raccogli celle attive (rivelate con vicini nascosti)
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
        
        # Confronta coppie
        for i in range(len(active_cells)):
            for j in range(len(active_cells)):
                if i == j: continue
                
                A = active_cells[i]
                B = active_cells[j]
                
                # Se A è sottoinsieme di B
                if A['hidden'].issubset(B['hidden']):
                    diff_set = B['hidden'] - A['hidden']
                    if not diff_set: continue
                        
                    mine_diff = B['remaining_mines'] - A['remaining_mines']
                    
                    if mine_diff == 0:
                        # Le celle extra sono sicure
                        for (dr, dc) in diff_set:
                            # print(f"AI: Adv Reveal ({dr}, {dc})")
                            self.game.reveal(dr, dc)
                            made_move = True
                    elif mine_diff == len(diff_set):
                        # Le celle extra sono mine
                        for (dr, dc) in diff_set:
                            # print(f"AI: Adv Flag ({dr}, {dc})")
                            self.game.toggle_flag(dr, dc)
                            made_move = True
        return made_move

    def make_guess(self):
        # Preferisci la frontiera
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
            # Caso iniziale o isolato: una cella a caso non rivelata
            hidden_cells = []
            for r in range(self.game.rows):
                for c in range(self.game.cols):
                    if not self.game.board[r][c].is_revealed and not self.game.board[r][c].is_flagged:
                        hidden_cells.append((r, c))
            if not hidden_cells: return
            gr, gc = random.choice(hidden_cells)
            
        # print(f"AI: Guessing ({gr}, {gc})")
        self.game.reveal(gr, gc)

    # Helper per GUI loop
    def run_gui_loop(self, root, gui_update_callback):
        if not self.running:
             # Primo click al centro
            center_r, center_c = self.game.rows // 2, self.game.cols // 2
            self.game.reveal(center_r, center_c)
            self.running = True
            gui_update_callback()
        
        if self.game.game_over:
            print("AI: Game Over")
            return

        self.step()
        gui_update_callback()
        
        # Pianifica il prossimo step
        root.after(100, lambda: self.run_gui_loop(root, gui_update_callback))

if __name__ == "__main__":
    root = tk.Tk()
    # Usa dimensioni ragionevoli per la demo
    app = MinesweeperGUI(root)
    
    # Crea AI
    ai = MinesweeperAI(app.game)
    
    # Avvia il loop AI
    root.after(1, lambda: ai.run_gui_loop(root, app.update_gui))
    
    root.mainloop()