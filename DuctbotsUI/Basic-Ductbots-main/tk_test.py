import tkinter as tk
from tkinter import filedialog
from kivy.app import App
from kivy.uix.button import Button
import threading

def select_folder(btn):
    def run_tk():
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(parent=root, title="Select Folder")
        root.destroy()
        print("Selected:", folder)
    
    # Run in a thread so Kivy doesn't block entirely, or just run directly
    # threading.Thread(target=run_tk).start()
    run_tk()

class TestApp(App):
    def build(self):
        b = Button(text="Select Folder")
        b.bind(on_press=select_folder)
        return b

if __name__ == '__main__':
    TestApp().run()
