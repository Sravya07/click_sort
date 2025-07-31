import os
import shutil
import datetime
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk, ExifTags
import cv2
import numpy as np

class PhotoSorter:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo Sorter")

        self.categories = ['reject', 'selected', 'favorites', 'maybe']
        self.photos = []
        self.current_index = 0
        self.hashes_seen = {}
        self.duplicate_pairs = []
        self.in_duplicate_mode = False

        self.folder = filedialog.askdirectory(title="Select a folder with photos")
        if not self.folder:
            exit()

        self.load_photos_and_detect_duplicates()

        self.image_label = tk.Label(root)
        self.image_label.pack()

        self.duplicate_frame = tk.Frame(root)
        self.duplicate_frame.pack()

        self.button_frame = tk.Frame(root)
        self.button_frame.pack(pady=10)

        self.status_label = tk.Label(root)
        self.status_label.pack()

        self.render_main_buttons()
        self.show_photo()

    def load_photos_and_detect_duplicates(self):
        files = [f for f in os.listdir(self.folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

        for f in files:
            path = os.path.join(self.folder, f)
            is_duplicate = False

            for seen in self.hashes_seen.values():
                seen_path = os.path.join(self.folder, seen)
                if self.are_images_similar(seen_path, path):
                    self.duplicate_pairs.append((seen, f))
                    is_duplicate = True
                    break

            if not is_duplicate:
                self.hashes_seen[f] = f
                self.photos.append(f)

        for cat in self.categories + ['duplicates']:
            os.makedirs(os.path.join(self.folder, cat), exist_ok=True)

    def are_images_similar(self, path1, path2, threshold=0.75):
        try:
            img1 = cv2.imread(path1, cv2.IMREAD_GRAYSCALE)
            img2 = cv2.imread(path2, cv2.IMREAD_GRAYSCALE)

            if img1 is None or img2 is None:
                return False

            orb = cv2.ORB_create()
            kp1, des1 = orb.detectAndCompute(img1, None)
            kp2, des2 = orb.detectAndCompute(img2, None)

            if des1 is None or des2 is None:
                return False

            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = bf.match(des1, des2)

            if not matches:
                return False

            matches = sorted(matches, key=lambda x: x.distance)
            similarity = len(matches) / min(len(kp1), len(kp2))

            return similarity > threshold
        except Exception as e:
            print(f"Error comparing images: {e}")
            return False

    def get_photo_taken_date(self, image_path):
        try:
            image = Image.open(image_path)
            exif_data = image._getexif()
            if exif_data:
                for tag, value in exif_data.items():
                    decoded = ExifTags.TAGS.get(tag, tag)
                    if decoded == "DateTimeOriginal":
                        return datetime.datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
        except Exception as e:
            print(f"EXIF read error for {image_path}: {e}")
        timestamp = os.path.getmtime(image_path)
        return datetime.datetime.fromtimestamp(timestamp)

    def show_photo(self):
        if self.duplicate_pairs:
            self.show_duplicate()
            return

        if self.current_index >= len(self.photos):
            self.image_label.config(text="All done!")
            return

        photo_path = os.path.join(self.folder, self.photos[self.current_index])
        img = Image.open(photo_path)
        img.thumbnail((600, 600))
        self.tk_img = ImageTk.PhotoImage(img)
        self.image_label.config(image=self.tk_img, text="")
        self.status_label.config(text=f"Sorting: {self.photos[self.current_index]}")

    def show_duplicate(self):
        self.in_duplicate_mode = True
        self.clear_frame(self.duplicate_frame)
        self.clear_frame(self.button_frame)

        original, duplicate = self.duplicate_pairs.pop(0)
        original_path = os.path.join(self.folder, original)
        duplicate_path = os.path.join(self.folder, duplicate)

        img1 = Image.open(original_path)
        img2 = Image.open(duplicate_path)
        img1.thumbnail((300, 300))
        img2.thumbnail((300, 300))

        self.tk_img1 = ImageTk.PhotoImage(img1)
        self.tk_img2 = ImageTk.PhotoImage(img2)

        tk.Label(self.duplicate_frame, text="Original").pack(side='left', padx=10)
        tk.Label(self.duplicate_frame, image=self.tk_img1).pack(side='left', padx=10)
        tk.Label(self.duplicate_frame, text="Duplicate").pack(side='left', padx=10)
        tk.Label(self.duplicate_frame, image=self.tk_img2).pack(side='left', padx=10)

        tk.Button(self.button_frame, text="Keep Both", command=lambda: self.keep_both(duplicate)).pack(side='left', padx=5)
        tk.Button(self.button_frame, text="Skip Duplicate", command=lambda: self.skip_duplicate(duplicate)).pack(side='left', padx=5)
        tk.Button(self.button_frame, text="Move to Duplicates", command=lambda: self.move_to_duplicates(duplicate)).pack(side='left', padx=5)

    def keep_both(self, duplicate):
        self.photos.append(duplicate)
        self.reset_after_duplicate()

    def skip_duplicate(self, duplicate):
        os.remove(os.path.join(self.folder, duplicate))
        self.reset_after_duplicate()

    def move_to_duplicates(self, duplicate):
        shutil.move(os.path.join(self.folder, duplicate), os.path.join(self.folder, 'duplicates', duplicate))
        self.reset_after_duplicate()

    def reset_after_duplicate(self):
        self.in_duplicate_mode = False
        self.clear_frame(self.duplicate_frame)
        self.render_main_buttons()
        self.show_photo()

    def sort_photo(self, category):
        if self.in_duplicate_mode:
            return

        file = self.photos[self.current_index]
        src_path = os.path.join(self.folder, file)

        if category == "selected":
            dt = self.get_photo_taken_date(src_path)
            year = str(dt.year)
            month = dt.strftime("%m-%B")
            dest_dir = os.path.join(self.folder, category, year, month)
        else:
            dest_dir = os.path.join(self.folder, category)

        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(src_path, os.path.join(dest_dir, file))

        self.current_index += 1
        self.show_photo()

    def render_main_buttons(self):
        self.clear_frame(self.button_frame)
        for cat in self.categories:
            tk.Button(self.button_frame, text=cat.capitalize(), width=10,
                      command=lambda c=cat: self.sort_photo(c)).pack(side='left', padx=5)

    def clear_frame(self, frame):
        for widget in frame.winfo_children():
            widget.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoSorter(root)
    root.mainloop()
