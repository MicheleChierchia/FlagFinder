import random
import sys
import os
import csv
import tkinter as tk

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.minesweeper import MinesweeperGUI

class MinesweeperAI:
    def __init__(self, game_logic):
        self.game = game_logic
        self.running = False
        self.csv_filename = 'minesweeper_dataset.csv'
        
        # 24 feature locali + 1 globale
        self.grid_features = [f"cell_{r}_{c}" for r in range(-2, 3) for c in range(-2, 3) if not (r==0 and c==0)]
        self.meta_features = ['global_density']
        self.dataset_columns = self.grid_features + self.meta_features
        
        if not os.path.exists(self.csv_filename):
            try:
                with open(self.csv_filename, mode='w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.dataset_columns + ['safe'])
            except IOError:
                pass

    def _get_effective_value(self, r, c):
        if not (0 <= r < self.game.rows and 0 <= c < self.game.cols):
            return -2 

        cell = self.game.board[r][c]
        if not cell.is_revealed:
            return -1 

        neighbors = self.game.get_neighbors(r, c)
        current_flags = len([n for n in neighbors if self.game.board[n[0]][n[1]].is_flagged])
        return cell.adjacent_mines - current_flags

    def _get_features_for_cell(self, r, c):
        features = []
        
        # Feature Locali (5x5)
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if dr == 0 and dc == 0: continue
                val = self._get_effective_value(r + dr, c + dc)
                features.append(val)
        
        # Feature Globale (Global Density)
        flags_on_board = 0
        revealed_on_board = 0
        total_cells = self.game.rows * self.game.cols
        
        for row in self.game.board:
            for cell in row:
                if cell.is_flagged: flags_on_board += 1
                if cell.is_revealed: revealed_on_board += 1
        
        mines_left = self.game.mines - flags_on_board
        hidden_cells = total_cells - revealed_on_board
        
        if hidden_cells > 0:
            density = mines_left / hidden_cells
        else:
            density = 0.0
            
        features.append(density)
        return features

    def _record_context(self, r, c, is_safe):
        data_row = self._get_features_for_cell(r, c)
        data_row.append(1 if is_safe else 0)
        
        try:
            with open(self.csv_filename, mode='a', newline='') as f:
                csv.writer(f).writerow(data_row)
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
                            self.game.toggle_flag(hr, hc)
                            made_move = True
                            
                    elif cell.adjacent_mines == flags:
                        for hr, hc in hidden:
                            self.game.reveal(hr, hc)
                            made_move = True

        if made_move: return True

        # 2. Logica Avanzata
        if self.run_advanced_logic(): return True

        # 3. Guessing (Salvataggio dati SOLO qui)
        self.make_guess()
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
                            self.game.toggle_flag(dr, dc)
                            made_move = True
        return made_move

    def make_guess(self):
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
            hidden = []
            for r in range(self.game.rows):
                for c in range(self.game.cols):
                    if not self.game.board[r][c].is_revealed and not self.game.board[r][c].is_flagged:
                        hidden.append((r, c))
            if not hidden: return
            gr, gc = random.choice(hidden)
            
        is_safe = not self.game.board[gr][gc].is_mine
        
        # Salvataggio dati
        self._record_context(gr, gc, is_safe=is_safe)
        
        self.game.reveal(gr, gc)

    def run_gui_loop(self, root, gui_update_callback):
        if not self.running:
            cr, cc = self.game.rows // 2, self.game.cols // 2
            self.game.reveal(cr, cc)
            self.running = True
            gui_update_callback()
        
        if self.game.game_over:
            # Scommentare per auto-restart
            # self.game.reset()
            # self.running = False
            return

        self.step()
        gui_update_callback()
        root.after(10, lambda: self.run_gui_loop(root, gui_update_callback))

if __name__ == "__main__":
    root = tk.Tk()
    app = MinesweeperGUI(root)
    ai = MinesweeperAI(app.game)
    root.after(100, lambda: ai.run_gui_loop(root, app.update_gui))
    root.mainloop()