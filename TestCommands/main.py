# -*- coding: utf-8 -*-

import tkinter as tk

from console_UI import TestConsole

if __name__ == '__main__':
    root = tk.Tk()
    root.title("Orin ARMM Test Console")
    tc = TestConsole(master = root)
    tc.mainloop()
