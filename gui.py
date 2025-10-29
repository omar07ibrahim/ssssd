"""
GUI module for LPR Counter-Surveillance System
Contains all UI components and dialogs
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from PIL import Image, ImageTk
from datetime import datetime
import json
import os
from threading import Lock
from config import logger, CONFIG, DISPLAY_CONFIG
from utils import format_duration, format_timestamp

class LPRMainWindow:
    """Main application window"""
    
    def __init__(self, root, app_controller):
        self.root = root
        self.app = app_controller
        self.root.title(DISPLAY_CONFIG['window_title'])
        self.root.geometry(DISPLAY_CONFIG['window_geometry'])
        
        # UI state
        self.search_var = tk.StringVar()
        self.current_photo = None
        
        # Setup UI
        self.setup_styles()
        self.setup_ui()
        self.setup_bindings()
        
    def setup_styles(self):
        """Configure ttk styles"""
        style = ttk.Style()
        style.configure('TFrame', background='#f0f0f0')
        style.configure('TLabel', background='#f0f0f0')
        style.configure('TButton', font=('Arial', 10))
        style.configure('Title.TLabel', font=('Arial', 14, 'bold'))
        style.configure('Status.TLabel', font=('Arial', 10, 'bold'))
        style.configure('Success.TLabel', foreground='green')
        style.configure('Warning.TLabel', foreground='orange')
        style.configure('Error.TLabel', foreground='red')
        
    def setup_ui(self):
        """Setup the main UI layout"""
        # Main container
        main_container = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel - Video and controls
        left_panel = ttk.Frame(main_container)
        main_container.add(left_panel, weight=1)
        self.setup_left_panel(left_panel)
        
        # Right panel - Results
        right_panel = ttk.Frame(main_container)
        main_container.add(right_panel, weight=2)
        self.setup_right_panel(right_panel)
        
        # Status bar
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def setup_left_panel(self, parent):
        """Setup left panel with video and controls"""
        # System status frame
        status_frame = ttk.LabelFrame(parent, text="System Status", padding=10)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Initializing...", style='Status.TLabel')
        self.status_label.pack(anchor='w')
        
        # Statistics frame
        stats_frame = ttk.Frame(status_frame)
        stats_frame.pack(fill=tk.X, pady=5)
        
        self.setup_statistics_display(stats_frame)
        
        # Video display
        video_frame = ttk.LabelFrame(parent, text="Live Feed", padding=5)
        video_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.video_label = ttk.Label(video_frame)
        self.video_label.pack(fill=tk.BOTH, expand=True)
        
        # Control buttons
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.setup_control_buttons(control_frame)
        
    def setup_statistics_display(self, parent):
        """Setup statistics display widgets"""
        # FPS
        ttk.Label(parent, text="FPS:").pack(side=tk.LEFT, padx=5)
        self.fps_label = ttk.Label(parent, text="0.0", width=6)
        self.fps_label.pack(side=tk.LEFT)
        
        # Frames processed
        ttk.Label(parent, text="Frames:").pack(side=tk.LEFT, padx=5)
        self.frames_label = ttk.Label(parent, text="0", width=8)
        self.frames_label.pack(side=tk.LEFT)
        
        # Plates detected
        ttk.Label(parent, text="Plates:").pack(side=tk.LEFT, padx=5)
        self.plates_label = ttk.Label(parent, text="0", width=8)
        self.plates_label.pack(side=tk.LEFT)
        
        # Queue size
        ttk.Label(parent, text="Queue:").pack(side=tk.LEFT, padx=5)
        self.queue_label = ttk.Label(parent, text="0", width=6)
        self.queue_label.pack(side=tk.LEFT)
        
    def setup_control_buttons(self, parent):
        """Setup control buttons"""
        # First row of buttons
        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=2)
        
        self.connect_btn = ttk.Button(
            row1, text="Connect Camera",
            command=self.app.connect_camera
        )
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = ttk.Button(
            row1, text="Pause",
            command=self.app.toggle_pause
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)

        # Display toggle button
        self.display_var = tk.BooleanVar(value=True)
        self.display_btn = ttk.Checkbutton(
            row1,
            text="Display",
            variable=self.display_var,
            command=self.toggle_display
        )
        self.display_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            row1, text="Settings",
            command=self.show_settings_dialog
        ).pack(side=tk.LEFT, padx=5)
        
        # Second row of buttons
        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=2)
        
        ttk.Button(
            row2, text="Blacklist",
            command=self.show_blacklist_manager
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            row2, text="Export",
            command=self.export_report
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            row2, text="Statistics",
            command=self.show_statistics
        ).pack(side=tk.LEFT, padx=5)
        
        # Exit button (red color)
        self.exit_btn = ttk.Button(
            row2, text="🛑 Stop & Exit",
            command=self.confirm_exit
        )
        self.exit_btn.pack(side=tk.RIGHT, padx=5)
        
    def setup_right_panel(self, parent):
        """Setup right panel with results"""
        # Title
        title_frame = ttk.Frame(parent)
        title_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(title_frame, text="License Plate Recognition", style='Title.TLabel').pack(side=tk.LEFT)
        
        # Quick stats
        self.quick_stats_label = ttk.Label(title_frame, text="")
        self.quick_stats_label.pack(side=tk.RIGHT, padx=10)
        
        # Search bar
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        search_entry.bind('<KeyRelease>', self.on_search)
        
        ttk.Button(search_frame, text="Clear", command=self.clear_search).pack(side=tk.LEFT, padx=5)
        
        # Results table
        results_frame = ttk.LabelFrame(parent, text="Real-Time Results", padding=5)
        results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.setup_results_table(results_frame)
        
    def setup_results_table(self, parent):
        """Setup results treeview table"""
        columns = ('Plate', 'Count', 'Last Seen', 'Duration', 'Confidence', 'Status')
        self.results_tree = ttk.Treeview(parent, columns=columns, show='headings', selectmode='browse')
        
        # Configure columns
        column_widths = {
            'Plate': 120,
            'Count': 60,
            'Last Seen': 100,
            'Duration': 80,
            'Confidence': 80,
            'Status': 100
        }
        
        for col in columns:
            self.results_tree.heading(col, text=col, command=lambda c=col: self.sort_results(c))
            self.results_tree.column(col, width=column_widths.get(col, 100))
        
        # Scrollbars
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.results_tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Pack treeview and scrollbars
        self.results_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        # Configure tags for color coding
        self.results_tree.tag_configure('blacklist', background='#ffcccc')
        self.results_tree.tag_configure('suspicious', background='#ffffcc')
        self.results_tree.tag_configure('new', background='#ccffcc')
        
        # Context menu
        self.setup_context_menu()
        
    def setup_context_menu(self):
        """Setup right-click context menu for results"""
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="View Details", command=self.view_plate_details)
        self.context_menu.add_command(label="View Images", command=self.view_plate_images)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Add to Blacklist", command=self.add_to_blacklist)
        self.context_menu.add_command(label="Remove from Blacklist", command=self.remove_from_blacklist)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Export Plate History", command=self.export_plate_history)
        
    def setup_bindings(self):
        """Setup event bindings"""
        self.results_tree.bind('<Double-1>', lambda e: self.view_plate_details())
        self.results_tree.bind('<Button-3>', self.show_context_menu)  # Right-click
        self.root.protocol("WM_DELETE_WINDOW", self.confirm_exit)
        
    def show_context_menu(self, event):
        """Show context menu on right-click"""
        try:
            # Select row under mouse
            item = self.results_tree.identify_row(event.y)
            if item:
                self.results_tree.selection_set(item)
                self.context_menu.post(event.x_root, event.y_root)
        except Exception as e:
            logger.error(f"Context menu error: {e}")
    
    def update_video_display(self, photo):
        """Update video display with new frame"""
        if hasattr(self.video_label, 'image') and self.video_label.image:
            self.video_label.image = None
        self.video_label.configure(image=photo)
        self.video_label.image = photo
        
    def update_status(self, status_text, status_type='normal'):
        """Update status label"""
        self.status_label.config(text=f"Status: {status_text}")
        
        # Apply style based on status type
        if status_type == 'success':
            self.status_label.configure(style='Success.TLabel')
        elif status_type == 'warning':
            self.status_label.configure(style='Warning.TLabel')
        elif status_type == 'error':
            self.status_label.configure(style='Error.TLabel')
        else:
            self.status_label.configure(style='Status.TLabel')
    
    def update_statistics(self, fps, frames, plates, queue_size=0):
        """Update statistics display"""
        self.fps_label.config(text=f"{fps:.1f}")
        self.frames_label.config(text=str(frames))
        self.plates_label.config(text=str(plates))
        self.queue_label.config(text=str(queue_size))
        
    def update_results(self, results):
        """Update results table with plate data"""
        # Clear existing items
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # Add new results
        for result in results:
            plate, count, last_seen, duration, confidence, status = result
            
            # Determine tags for row
            tags = []
            if 'BLACKLIST' in status:
                tags.append('blacklist')
            elif 'SUSPICIOUS' in status:
                tags.append('suspicious')
            elif count == 1:
                tags.append('new')
            
            # Insert row
            self.results_tree.insert('', 'end', values=(
                plate, count, last_seen, duration, confidence, status
            ), tags=tags)
        
        # Update quick stats
        total_plates = len(results)
        blacklisted = sum(1 for r in results if 'BLACKLIST' in r[5])
        suspicious = sum(1 for r in results if 'SUSPICIOUS' in r[5])
        self.quick_stats_label.config(
            text=f"Total: {total_plates} | Blacklist: {blacklisted} | Suspicious: {suspicious}"
        )
    
    def on_search(self, event=None):
        """Handle search input"""
        self.app.search_plates(self.search_var.get())
        
    def clear_search(self):
        """Clear search input"""
        self.search_var.set("")
        self.app.search_plates("")
    
    def sort_results(self, column):
        """Sort results by column"""
        # TODO: Implement sorting
        pass
    
    def view_plate_details(self):
        """Show detailed plate information"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        plate_text = item['values'][0]
        
        PlateDetailsDialog(self.root, self.app, plate_text)
    
    def view_plate_images(self):
        """View plate detection images"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        plate_text = item['values'][0]
        
        PlateImagesDialog(self.root, self.app, plate_text)
    
    def add_to_blacklist(self):
        """Add selected plate to blacklist"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        plate_text = item['values'][0]
        
        BlacklistAddDialog(self.root, self.app, plate_text)
    
    def remove_from_blacklist(self):
        """Remove selected plate from blacklist"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        plate_text = item['values'][0]
        
        self.app.remove_from_blacklist(plate_text)
        self.app.update_results()
    
    def export_plate_history(self):
        """Export selected plate history"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        plate_text = item['values'][0]
        
        self.app.export_plate_history(plate_text)
    
    def show_settings_dialog(self):
        """Show settings dialog"""
        SettingsDialog(self.root, self.app)
    
    def show_blacklist_manager(self):
        """Show blacklist manager dialog"""
        BlacklistManagerDialog(self.root, self.app)
    
    def show_statistics(self):
        """Show statistics dialog"""
        StatisticsDialog(self.root, self.app)
    
    def export_report(self):
        """Export report dialog"""
        ExportDialog(self.root, self.app)
    
    def set_pause_state(self, is_paused):
        """Update pause button state"""
        self.pause_btn.config(text="Resume" if is_paused else "Pause")
        self.status_bar.config(text=f"System status: {'PAUSED' if is_paused else 'ACTIVE'}")
        
    def set_connection_state(self, is_connected):
        """Update connection button state"""
        if is_connected:
            self.connect_btn.config(text="Disconnect", state='normal')
        else:
            self.connect_btn.config(text="Connect Camera", state='normal')
    
    def confirm_exit(self):
        """Confirm and execute exit"""
        if messagebox.askyesno("Exit", "Are you sure you want to stop and exit the application?"):
            self.app.on_closing()

    def toggle_display(self):
        """Toggle GUI video display ON/OFF"""
        enabled = self.display_var.get()
        if hasattr(self.app, 'camera') and self.app.camera:
            self.app.camera.toggle_display(enabled)

        # Update video label
        if not enabled:
            self.video_label.configure(image='', text='Display OFF (saving CPU)')
        else:
            self.video_label.configure(text='')


class PlateDetailsDialog:
    """Dialog for showing detailed plate information"""
    
    def __init__(self, parent, app, plate_text):
        self.app = app
        self.plate_text = plate_text
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Plate Details: {plate_text}")
        self.dialog.geometry("800x600")
        self.dialog.transient(parent)
        
        self.setup_ui()
        self.load_data()
        
    def setup_ui(self):
        """Setup dialog UI"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Information tab
        self.info_frame = ttk.Frame(notebook)
        notebook.add(self.info_frame, text="Information")
        self.setup_info_tab()
        
        # History tab
        self.history_frame = ttk.Frame(notebook)
        notebook.add(self.history_frame, text="Detection History")
        self.setup_history_tab()
        
        # Images tab
        self.images_frame = ttk.Frame(notebook)
        notebook.add(self.images_frame, text="Images")
        self.setup_images_tab()
        
        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Export", command=self.export_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        
    def setup_info_tab(self):
        """Setup information tab"""
        self.info_text = scrolledtext.ScrolledText(self.info_frame, wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
    def setup_history_tab(self):
        """Setup history tab with tree structure for grouped detections"""
        # Create paned window for split view
        paned = ttk.PanedWindow(self.history_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left side - detection list
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=2)
        
        # Create treeview for history with tree support
        columns = ('Time', 'Raw Text', 'Confidence', 'Time Diff')
        self.history_tree = ttk.Treeview(left_frame, columns=columns, show='tree headings')
        
        # Configure columns
        self.history_tree.heading('#0', text='Group')
        self.history_tree.column('#0', width=50)
        
        for col in columns:
            self.history_tree.heading(col, text=col)
            if col == 'Time':
                self.history_tree.column(col, width=150)
            elif col == 'Time Diff':
                self.history_tree.column(col, width=80)
            else:
                self.history_tree.column(col, width=150)
        
        # Scrollbar
        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=vsb.set)
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Right side - details panel
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        
        # Timestamp label
        self.detail_time_label = ttk.Label(right_frame, text="Select a detection", font=('Arial', 12, 'bold'))
        self.detail_time_label.pack(pady=10)
        
        # Hint label
        self.hint_label = ttk.Label(right_frame, text="Click on image to zoom", font=('Arial', 9, 'italic'))
        self.hint_label.pack()
        
        # Image display
        self.detail_image_label = ttk.Label(right_frame, text="No image available")
        self.detail_image_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Bind selection event
        self.history_tree.bind('<<TreeviewSelect>>', self.on_history_select)
        
    def setup_images_tab(self):
        """Setup images tab"""
        self.image_label = ttk.Label(self.images_frame, text="Loading images...")
        self.image_label.pack(pady=10)
        
    def load_data(self):
        """Load plate data from database"""
        # Get plate information
        plate_info = self.app.db.get_plate_info(self.plate_text)
        if plate_info:
            self.display_info(plate_info)
        
        # Get detection history
        detections = self.app.db.get_plate_detections(self.plate_text, limit=100)
        self.display_history(detections)
        
        # Load images if available
        if plate_info and plate_info[8]:  # last_detection_image_path
            self.load_image(plate_info[8])
    
    def display_info(self, plate_info):
        """Display plate information"""
        info_text = f"""
Plate Number: {self.plate_text}
First Seen: {format_timestamp(plate_info[1])}
Last Seen: {format_timestamp(plate_info[2])}
Detection Count: {plate_info[3]}
Country Code: {plate_info[4] or 'Unknown'}
Highest Confidence: {plate_info[5]}%
Suspicious: {'Yes' if plate_info[6] else 'No'}
Blacklisted: {'Yes' if plate_info[7] else 'No'}

Duration Present: {format_duration((datetime.fromisoformat(plate_info[2]) - datetime.fromisoformat(plate_info[1])).total_seconds())}
"""
        
        self.info_text.delete('1.0', tk.END)
        self.info_text.insert('1.0', info_text)
        self.info_text.config(state='disabled')
    
    def display_history(self, detections):
        """Display detection history with grouping"""
        # Clear existing items
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        # Store detection data for later access
        self.detection_data = {}
        
        # Get grouped detections from database
        grouped = self.app.db.get_grouped_detections(self.plate_text, limit=100)
        
        for group in grouped:
            # Insert parent detection
            parent_values = (
                format_timestamp(group['timestamp'], '%Y-%m-%d %H:%M:%S'),
                group['text'],
                f"{group['confidence']:.1f}%",
                ""  # No time diff for parent
            )
            
            parent_item = self.history_tree.insert('', 'end', 
                text='▼' if group['children'] else '●',
                values=parent_values,
                open=False,  # Start collapsed
                tags=('has_image',) if group.get('image_path') else ()
            )
            
            # Store detection data
            self.detection_data[parent_item] = {
                'timestamp': group['timestamp'],
                'image_path': group.get('image_path'),
                'confidence': group['confidence'],
                'text': group['text']
            }
            
            # Insert child detections
            for child in group['children']:
                child_values = (
                    format_timestamp(child['timestamp'], '%H:%M:%S'),
                    child['text'],
                    f"{child['confidence']:.1f}%",
                    f"+{child['time_diff']}s"
                )
                
                child_item = self.history_tree.insert(parent_item, 'end',
                    text='└─',
                    values=child_values
                )
                
                # Store child detection data (no image for grouped items)
                self.detection_data[child_item] = {
                    'timestamp': child['timestamp'],
                    'image_path': None,
                    'confidence': child['confidence'],
                    'text': child['text']
                }
    
    def load_image(self, image_path):
        """Load and display image"""
        try:
            image = Image.open(image_path)
            image.thumbnail((600, 400), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            
            self.image_label.configure(image=photo, text="")
            self.image_label.image = photo
        except Exception as e:
            self.image_label.configure(text=f"Error loading image: {e}")
    
    def on_history_select(self, event):
        """Handle selection in history tree"""
        selection = self.history_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        if item_id in self.detection_data:
            data = self.detection_data[item_id]
            
            # Update timestamp display
            timestamp_str = format_timestamp(data['timestamp'], '%Y-%m-%d %H:%M:%S')
            self.detail_time_label.config(text=f"Time: {timestamp_str}")
            
            # Store original image path for zoom
            self.current_image_path = data.get('image_path')
            
            # Load and display image if available
            if self.current_image_path and os.path.exists(self.current_image_path):
                try:
                    # Load image
                    image = Image.open(self.current_image_path)
                    # Store original for zoom
                    self.original_image = image.copy()
                    # Resize to fit panel
                    image.thumbnail((400, 300), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    
                    # Update image label
                    self.detail_image_label.configure(image=photo, text="", cursor="hand2")
                    self.detail_image_label.image = photo
                    
                    # Bind click for zoom
                    self.detail_image_label.unbind("<Button-1>")
                    self.detail_image_label.bind("<Button-1>", self.show_zoomed_image)
                except Exception as e:
                    self.detail_image_label.configure(image="", text=f"Error loading image: {e}", cursor="")
                    self.detail_image_label.unbind("<Button-1>")
            else:
                self.detail_image_label.configure(image="", text="No image available for this detection", cursor="")
                self.detail_image_label.unbind("<Button-1>")
    
    def show_zoomed_image(self, event=None):
        """Show zoomed image in a new window"""
        if not hasattr(self, 'original_image'):
            return
        
        # Create zoom window
        zoom_window = tk.Toplevel(self.dialog)
        zoom_window.title(f"Zoomed Image - {self.plate_text}")
        zoom_window.transient(self.dialog)
        
        # Get screen dimensions
        screen_width = zoom_window.winfo_screenwidth()
        screen_height = zoom_window.winfo_screenheight()
        
        # Calculate window size (80% of screen)
        window_width = int(screen_width * 0.8)
        window_height = int(screen_height * 0.8)
        
        # Center window
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        zoom_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Create canvas for scrollable image
        canvas = tk.Canvas(zoom_window, bg='black')
        canvas.pack(fill=tk.BOTH, expand=True)
        
        # Add scrollbars
        v_scrollbar = ttk.Scrollbar(zoom_window, orient='vertical', command=canvas.yview)
        h_scrollbar = ttk.Scrollbar(zoom_window, orient='horizontal', command=canvas.xview)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Create frame for image and controls
        frame = ttk.Frame(canvas)
        canvas_frame = canvas.create_window(0, 0, anchor='nw', window=frame)
        
        # Control buttons
        control_frame = ttk.Frame(frame)
        control_frame.pack(pady=10)
        
        zoom_level = tk.DoubleVar(value=1.0)
        
        def update_zoom(value=None):
            """Update image zoom"""
            try:
                scale = zoom_level.get()
                new_size = (
                    int(self.original_image.width * scale),
                    int(self.original_image.height * scale)
                )
                resized = self.original_image.resize(new_size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(resized)
                image_label.configure(image=photo)
                image_label.image = photo
                
                # Update scroll region
                frame.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox('all'))
            except Exception as e:
                print(f"Zoom error: {e}")
        
        ttk.Label(control_frame, text="Zoom:").pack(side=tk.LEFT, padx=5)
        zoom_scale = ttk.Scale(control_frame, from_=0.5, to=3.0, orient=tk.HORIZONTAL,
                              variable=zoom_level, command=update_zoom, length=200)
        zoom_scale.pack(side=tk.LEFT, padx=5)
        zoom_label = ttk.Label(control_frame, text="100%")
        zoom_label.pack(side=tk.LEFT, padx=5)
        
        def update_zoom_label(value=None):
            zoom_label.config(text=f"{int(zoom_level.get() * 100)}%")
            update_zoom()
        
        zoom_scale.configure(command=update_zoom_label)
        
        ttk.Button(control_frame, text="Reset", command=lambda: zoom_level.set(1.0)).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Close", command=zoom_window.destroy).pack(side=tk.LEFT, padx=20)
        
        # Display image
        image_label = ttk.Label(frame)
        image_label.pack(padx=10, pady=10)
        
        # Initial display
        update_zoom()
        
        # Enable mouse wheel zoom
        def on_mousewheel(event):
            if event.delta > 0:
                zoom_level.set(min(3.0, zoom_level.get() + 0.1))
            else:
                zoom_level.set(max(0.5, zoom_level.get() - 0.1))
            update_zoom_label()
        
        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", lambda e: on_mousewheel(type('', (), {'delta': 1})()))
        canvas.bind("<Button-5>", lambda e: on_mousewheel(type('', (), {'delta': -1})()))
    
    def export_data(self):
        """Export plate data"""
        self.app.export_plate_history(self.plate_text)


class SettingsDialog:
    """Comprehensive settings dialog"""
    
    def __init__(self, parent, app):
        self.app = app
        self.settings_vars = {}
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("System Settings")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        """Setup settings UI with tabs"""
        # Create notebook
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Camera settings tab
        self.setup_camera_tab(notebook)
        
        # LPR settings tab
        self.setup_lpr_tab(notebook)
        
        # Alert settings tab
        self.setup_alert_tab(notebook)
        
        # Preprocessing settings tab
        self.setup_preprocessing_tab(notebook)
        
        # Validation settings tab
        self.setup_validation_tab(notebook)
        
        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Save", command=self.save_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Reset to Defaults", command=self.reset_defaults).pack(side=tk.LEFT, padx=5)
    
    def setup_camera_tab(self, notebook):
        """Setup camera settings tab"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Camera")
        
        # Camera index
        ttk.Label(frame, text="Camera Index:").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['camera_index'] = tk.IntVar()
        ttk.Spinbox(frame, from_=0, to=10, textvariable=self.settings_vars['camera_index']).grid(
            row=0, column=1, padx=10, pady=5, sticky='ew')
        
        # Resolution
        ttk.Label(frame, text="Resolution:").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['resolution'] = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.settings_vars['resolution'],
                    values=['640x480', '1280x720', '1920x1080', '2560x1440']).grid(
            row=1, column=1, padx=10, pady=5, sticky='ew')

        # Display Skip Rate
        ttk.Label(frame, text="Display Update Rate:").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['display_skip_rate'] = tk.IntVar()
        skip_frame = ttk.Frame(frame)
        skip_frame.grid(row=2, column=1, padx=10, pady=5, sticky='ew')
        ttk.Spinbox(skip_frame, from_=1, to=10, textvariable=self.settings_vars['display_skip_rate'], width=5).pack(side=tk.LEFT)
        ttk.Label(skip_frame, text="(1=every frame, 2=every 2nd, etc)", font=('', 8)).pack(side=tk.LEFT, padx=5)

        # Virtual Camera Skip Rate
        ttk.Label(frame, text="Virtual Camera Update Rate:").grid(row=3, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['virtual_camera_skip_rate'] = tk.IntVar()
        vcam_frame = ttk.Frame(frame)
        vcam_frame.grid(row=3, column=1, padx=10, pady=5, sticky='ew')
        ttk.Spinbox(vcam_frame, from_=1, to=10, textvariable=self.settings_vars['virtual_camera_skip_rate'], width=5).pack(side=tk.LEFT)
        ttk.Label(vcam_frame, text="(1=every frame, 2=every 2nd, etc)", font=('', 8)).pack(side=tk.LEFT, padx=5)

        # Auto-connect camera on startup
        self.settings_vars['auto_connect_camera'] = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="✅ Auto-connect camera on startup",
            variable=self.settings_vars['auto_connect_camera']
        ).grid(row=4, column=0, columnspan=2, padx=10, pady=10, sticky='w')

        frame.columnconfigure(1, weight=1)
    
    def setup_lpr_tab(self, notebook):
        """Setup LPR settings tab"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="LPR")
        
        # Min plate width
        ttk.Label(frame, text="Min Plate Width:").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['min_plate_width'] = tk.IntVar()
        ttk.Spinbox(frame, from_=10, to=200, textvariable=self.settings_vars['min_plate_width']).grid(
            row=0, column=1, padx=10, pady=5, sticky='ew')
        
        # Max plate width
        ttk.Label(frame, text="Max Plate Width:").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['max_plate_width'] = tk.IntVar()
        ttk.Spinbox(frame, from_=100, to=800, textvariable=self.settings_vars['max_plate_width']).grid(
            row=1, column=1, padx=10, pady=5, sticky='ew')
        
        # Countries
        ttk.Label(frame, text="Countries:").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['countries'] = tk.StringVar()
        ttk.Entry(frame, textvariable=self.settings_vars['countries']).grid(
            row=2, column=1, padx=10, pady=5, sticky='ew')
        
        # FPS limit
        ttk.Label(frame, text="FPS Limit (0=unlimited):").grid(row=3, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['fps_limit'] = tk.IntVar()
        ttk.Spinbox(frame, from_=0, to=60, textvariable=self.settings_vars['fps_limit']).grid(
            row=3, column=1, padx=10, pady=5, sticky='ew')
        
        # Levenshtein threshold
        ttk.Label(frame, text="Similarity Threshold:").grid(row=4, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['levenshtein_threshold'] = tk.IntVar()
        ttk.Spinbox(frame, from_=0, to=5, textvariable=self.settings_vars['levenshtein_threshold']).grid(
            row=4, column=1, padx=10, pady=5, sticky='ew')
        
        frame.columnconfigure(1, weight=1)
    
    def setup_alert_tab(self, notebook):
        """Setup alert settings tab"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Alerts")
        
        # Suspicious duration
        ttk.Label(frame, text="Suspicious Duration (min):").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['suspicious_duration_minutes'] = tk.IntVar()
        ttk.Spinbox(frame, from_=1, to=60, textvariable=self.settings_vars['suspicious_duration_minutes']).grid(
            row=0, column=1, padx=10, pady=5, sticky='ew')
        
        # Telegram enabled
        self.settings_vars['telegram_enabled'] = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Enable Telegram Notifications",
                       variable=self.settings_vars['telegram_enabled']).grid(
            row=1, column=0, columnspan=2, padx=10, pady=5, sticky='w')
        
        # Save images
        self.settings_vars['save_images'] = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Save Detection Images",
                       variable=self.settings_vars['save_images']).grid(
            row=2, column=0, columnspan=2, padx=10, pady=5, sticky='w')
        
        # Image quality
        ttk.Label(frame, text="Image Quality:").grid(row=3, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['image_quality'] = tk.IntVar()
        quality_frame = ttk.Frame(frame)
        quality_frame.grid(row=3, column=1, padx=10, pady=5, sticky='ew')
        
        ttk.Scale(quality_frame, from_=50, to=100, orient=tk.HORIZONTAL,
                 variable=self.settings_vars['image_quality']).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(quality_frame, textvariable=self.settings_vars['image_quality']).pack(side=tk.LEFT, padx=5)

        # Blacklist Similarity Threshold
        ttk.Label(frame, text="Blacklist Match Threshold (%):").grid(row=4, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['blacklist_similarity_threshold'] = tk.IntVar()
        threshold_frame = ttk.Frame(frame)
        threshold_frame.grid(row=4, column=1, padx=10, pady=5, sticky='ew')

        ttk.Scale(threshold_frame, from_=70, to=100, orient=tk.HORIZONTAL,
                 variable=self.settings_vars['blacklist_similarity_threshold']).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(threshold_frame, textvariable=self.settings_vars['blacklist_similarity_threshold']).pack(side=tk.LEFT, padx=5)
        ttk.Label(threshold_frame, text="%", font=('', 8)).pack(side=tk.LEFT)

        frame.columnconfigure(1, weight=1)
    
    def setup_preprocessing_tab(self, notebook):
        """Setup preprocessing settings tab"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Preprocessing")
        
        # Contrast
        ttk.Label(frame, text="Contrast:").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['contrast'] = tk.DoubleVar()
        contrast_frame = ttk.Frame(frame)
        contrast_frame.grid(row=0, column=1, padx=10, pady=5, sticky='ew')
        
        ttk.Scale(contrast_frame, from_=0.5, to=2.0, orient=tk.HORIZONTAL,
                 variable=self.settings_vars['contrast']).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(contrast_frame, textvariable=self.settings_vars['contrast']).pack(side=tk.LEFT, padx=5)
        
        # Brightness
        ttk.Label(frame, text="Brightness:").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['brightness'] = tk.DoubleVar()
        brightness_frame = ttk.Frame(frame)
        brightness_frame.grid(row=1, column=1, padx=10, pady=5, sticky='ew')
        
        ttk.Scale(brightness_frame, from_=0.5, to=2.0, orient=tk.HORIZONTAL,
                 variable=self.settings_vars['brightness']).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(brightness_frame, textvariable=self.settings_vars['brightness']).pack(side=tk.LEFT, padx=5)
        
        # Sharpness
        ttk.Label(frame, text="Sharpness:").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['sharpness'] = tk.DoubleVar()
        sharpness_frame = ttk.Frame(frame)
        sharpness_frame.grid(row=2, column=1, padx=10, pady=5, sticky='ew')
        
        ttk.Scale(sharpness_frame, from_=0.5, to=2.0, orient=tk.HORIZONTAL,
                 variable=self.settings_vars['sharpness']).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(sharpness_frame, textvariable=self.settings_vars['sharpness']).pack(side=tk.LEFT, padx=5)
        
        frame.columnconfigure(1, weight=1)
    
    def setup_validation_tab(self, notebook):
        """Setup validation settings tab"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Validation")
        
        # Min plate length
        ttk.Label(frame, text="Min Plate Length:").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['min_length'] = tk.IntVar()
        ttk.Spinbox(frame, from_=1, to=15, textvariable=self.settings_vars['min_length']).grid(
            row=0, column=1, padx=10, pady=5, sticky='ew')
        
        # Max plate length
        ttk.Label(frame, text="Max Plate Length:").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['max_length'] = tk.IntVar()
        ttk.Spinbox(frame, from_=5, to=20, textvariable=self.settings_vars['max_length']).grid(
            row=1, column=1, padx=10, pady=5, sticky='ew')
        
        # Allowed characters
        ttk.Label(frame, text="Allowed Characters:").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        self.settings_vars['allowed_chars'] = tk.StringVar()
        ttk.Entry(frame, textvariable=self.settings_vars['allowed_chars']).grid(
            row=2, column=1, padx=10, pady=5, sticky='ew')
        
        frame.columnconfigure(1, weight=1)
    
    def load_settings(self):
        """Load current settings into variables"""
        # Camera settings
        self.settings_vars['camera_index'].set(CONFIG.get('camera_index', 0))
        resolution = f"{CONFIG.get('camera_width', 1920)}x{CONFIG.get('camera_height', 1080)}"
        self.settings_vars['resolution'].set(resolution)
        self.settings_vars['display_skip_rate'].set(CONFIG.get('display_skip_rate', 2))
        self.settings_vars['virtual_camera_skip_rate'].set(CONFIG.get('virtual_camera_skip_rate', 2))
        self.settings_vars['auto_connect_camera'].set(CONFIG.get('auto_connect_camera', False))
        
        # LPR settings
        self.settings_vars['min_plate_width'].set(CONFIG.get('min_plate_width', 80))
        self.settings_vars['max_plate_width'].set(CONFIG.get('max_plate_width', 400))
        self.settings_vars['countries'].set(CONFIG.get('countries', ''))
        self.settings_vars['fps_limit'].set(CONFIG.get('fps_limit', 0))
        self.settings_vars['levenshtein_threshold'].set(CONFIG.get('levenshtein_threshold', 2))
        
        # Alert settings
        self.settings_vars['suspicious_duration_minutes'].set(CONFIG.get('suspicious_duration_minutes', 2))
        self.settings_vars['telegram_enabled'].set(CONFIG.get('telegram_enabled', True))
        self.settings_vars['save_images'].set(CONFIG.get('save_images', True))
        self.settings_vars['image_quality'].set(CONFIG.get('image_quality', 95))
        self.settings_vars['blacklist_similarity_threshold'].set(CONFIG.get('blacklist_similarity_threshold', 80))
        
        # Preprocessing settings
        preprocessing = CONFIG.get('preprocessing', {})
        self.settings_vars['contrast'].set(preprocessing.get('contrast', 1.0))
        self.settings_vars['brightness'].set(preprocessing.get('brightness', 1.0))
        self.settings_vars['sharpness'].set(preprocessing.get('sharpness', 1.0))
        
        # Validation settings
        validation = CONFIG.get('plate_validation', {})
        self.settings_vars['min_length'].set(validation.get('min_length', 3))
        self.settings_vars['max_length'].set(validation.get('max_length', 10))
        self.settings_vars['allowed_chars'].set(validation.get('allowed_chars', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'))
    
    def save_settings(self):
        """Save settings and apply changes"""
        try:
            # Camera settings
            CONFIG['camera_index'] = self.settings_vars['camera_index'].get()
            res_parts = self.settings_vars['resolution'].get().split('x')
            if len(res_parts) == 2:
                CONFIG['camera_width'] = int(res_parts[0])
                CONFIG['camera_height'] = int(res_parts[1])
            CONFIG['display_skip_rate'] = self.settings_vars['display_skip_rate'].get()
            CONFIG['virtual_camera_skip_rate'] = self.settings_vars['virtual_camera_skip_rate'].get()
            CONFIG['auto_connect_camera'] = self.settings_vars['auto_connect_camera'].get()

            # Apply skip rates to camera if connected
            if hasattr(self.app, 'camera') and self.app.camera:
                self.app.camera.set_display_skip_rate(CONFIG['display_skip_rate'])
                self.app.camera.set_virtual_camera_skip_rate(CONFIG['virtual_camera_skip_rate'])

            # LPR settings
            CONFIG['min_plate_width'] = self.settings_vars['min_plate_width'].get()
            CONFIG['max_plate_width'] = self.settings_vars['max_plate_width'].get()
            CONFIG['countries'] = self.settings_vars['countries'].get()
            CONFIG['fps_limit'] = self.settings_vars['fps_limit'].get()
            CONFIG['levenshtein_threshold'] = self.settings_vars['levenshtein_threshold'].get()
            
            # Alert settings
            CONFIG['suspicious_duration_minutes'] = self.settings_vars['suspicious_duration_minutes'].get()
            CONFIG['telegram_enabled'] = self.settings_vars['telegram_enabled'].get()
            CONFIG['save_images'] = self.settings_vars['save_images'].get()
            CONFIG['image_quality'] = self.settings_vars['image_quality'].get()
            CONFIG['blacklist_similarity_threshold'] = self.settings_vars['blacklist_similarity_threshold'].get()
            
            # Preprocessing settings
            CONFIG['preprocessing']['contrast'] = self.settings_vars['contrast'].get()
            CONFIG['preprocessing']['brightness'] = self.settings_vars['brightness'].get()
            CONFIG['preprocessing']['sharpness'] = self.settings_vars['sharpness'].get()
            
            # Validation settings
            CONFIG['plate_validation']['min_length'] = self.settings_vars['min_length'].get()
            CONFIG['plate_validation']['max_length'] = self.settings_vars['max_length'].get()
            CONFIG['plate_validation']['allowed_chars'] = self.settings_vars['allowed_chars'].get()
            
            # Apply settings
            self.app.apply_settings()
            
            messagebox.showinfo("Settings", "Settings saved successfully!")
            self.dialog.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
    
    def reset_defaults(self):
        """Reset settings to default values"""
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset all settings to defaults?"):
            # Reset CONFIG to defaults
            # TODO: Implement default settings reset
            self.load_settings()


class BlacklistAddDialog:
    """Dialog for adding plate to blacklist"""
    
    def __init__(self, parent, app, plate_text):
        self.app = app
        self.plate_text = plate_text
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Add {plate_text} to Blacklist")
        self.dialog.geometry("400x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup dialog UI"""
        ttk.Label(self.dialog, text=f"Plate: {self.plate_text}").pack(pady=10)
        
        # Reason
        ttk.Label(self.dialog, text="Reason:").pack(anchor=tk.W, padx=10)
        self.reason_var = tk.StringVar()
        ttk.Entry(self.dialog, textvariable=self.reason_var, width=40).pack(padx=10, pady=5)
        
        # Danger level
        ttk.Label(self.dialog, text="Danger Level:").pack(anchor=tk.W, padx=10)
        self.danger_var = tk.StringVar(value="MEDIUM")
        ttk.Combobox(self.dialog, textvariable=self.danger_var,
                    values=["LOW", "MEDIUM", "HIGH", "CRITICAL"]).pack(padx=10, pady=5)
        
        # Notes
        ttk.Label(self.dialog, text="Notes:").pack(anchor=tk.W, padx=10)
        self.notes_text = scrolledtext.ScrolledText(self.dialog, width=40, height=5)
        self.notes_text.pack(padx=10, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Add", command=self.add_to_blacklist).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
    def add_to_blacklist(self):
        """Add plate to blacklist"""
        reason = self.reason_var.get().strip()
        if not reason:
            messagebox.showerror("Error", "Reason is required")
            return
        
        danger = self.danger_var.get()
        notes = self.notes_text.get("1.0", tk.END).strip()
        
        if self.app.db.add_to_blacklist(self.plate_text, reason, danger, notes):
            messagebox.showinfo("Success", f"{self.plate_text} added to blacklist")
            self.dialog.destroy()
            self.app.update_results()
        else:
            messagebox.showerror("Error", "Failed to add plate to blacklist")


class BlacklistManagerDialog:
    """Dialog for managing blacklisted plates"""
    
    def __init__(self, parent, app):
        self.app = app
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Blacklist Manager")
        self.dialog.geometry("700x500")
        self.dialog.transient(parent)
        
        self.setup_ui()
        self.load_blacklist()
    
    def setup_ui(self):
        """Setup dialog UI"""
        # Toolbar
        toolbar = ttk.Frame(self.dialog)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(toolbar, text="Add", command=self.add_plate).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Remove", command=self.remove_plate).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Import", command=self.import_blacklist).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Export", command=self.export_blacklist).pack(side=tk.LEFT, padx=5)
        
        # Blacklist table
        columns = ('Plate', 'Reason', 'Danger Level', 'Date Added')
        self.blacklist_tree = ttk.Treeview(self.dialog, columns=columns, show='headings')
        
        for col in columns:
            self.blacklist_tree.heading(col, text=col)
            self.blacklist_tree.column(col, width=150)
        
        # Scrollbar
        vsb = ttk.Scrollbar(self.dialog, orient="vertical", command=self.blacklist_tree.yview)
        self.blacklist_tree.configure(yscrollcommand=vsb.set)
        
        self.blacklist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=10)
        
        # Close button
        ttk.Button(self.dialog, text="Close", command=self.dialog.destroy).pack(pady=10)
    
    def load_blacklist(self):
        """Load blacklist from database"""
        # Clear existing items
        for item in self.blacklist_tree.get_children():
            self.blacklist_tree.delete(item)
        
        # Load from database
        blacklist_data = self.app.db.get_all_blacklist()
        
        for plate_data in blacklist_data:
            plate_text, reason, danger_level, date_added, notes = plate_data
            # Format date if it's a datetime object
            if hasattr(date_added, 'strftime'):
                formatted_date = date_added.strftime('%Y-%m-%d %H:%M')
            else:
                formatted_date = str(date_added)[:16]  # Truncate string if needed
            
            self.blacklist_tree.insert('', 'end', values=(
                plate_text, reason, danger_level, formatted_date
            ))
    
    def add_plate(self):
        """Add new plate to blacklist"""
        dialog = tk.Toplevel(self.dialog)
        dialog.title("Add Plate to Blacklist")
        dialog.geometry("450x400")
        dialog.transient(self.dialog)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Plate text
        ttk.Label(dialog, text="Plate Number:").pack(anchor=tk.W, padx=10, pady=5)
        plate_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=plate_var, width=40).pack(padx=10, pady=5)
        
        # Reason
        ttk.Label(dialog, text="Reason:").pack(anchor=tk.W, padx=10, pady=5)
        reason_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=reason_var, width=40).pack(padx=10, pady=5)
        
        # Danger level
        ttk.Label(dialog, text="Danger Level:").pack(anchor=tk.W, padx=10, pady=5)
        danger_var = tk.StringVar(value="MEDIUM")
        ttk.Combobox(dialog, textvariable=danger_var,
                    values=["LOW", "MEDIUM", "HIGH", "CRITICAL"]).pack(padx=10, pady=5)
        
        # Notes
        ttk.Label(dialog, text="Notes:").pack(anchor=tk.W, padx=10, pady=5)
        notes_text = scrolledtext.ScrolledText(dialog, width=40, height=4)
        notes_text.pack(padx=10, pady=(5, 10))
        
        def add_action():
            plate = plate_var.get().strip().upper()
            reason = reason_var.get().strip()
            if not plate or not reason:
                messagebox.showerror("Error", "Plate number and reason are required")
                return
            
            danger = danger_var.get()
            notes = notes_text.get("1.0", tk.END).strip()
            
            if self.app.db.add_to_blacklist(plate, reason, danger, notes):
                messagebox.showinfo("Success", f"{plate} added to blacklist")
                dialog.destroy()
                self.load_blacklist()  # Refresh the list
            else:
                messagebox.showerror("Error", "Failed to add plate to blacklist")
        
        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=15)
        
        # Cancel button (left side)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Add button (right side)
        ttk.Button(button_frame, text="Add", command=add_action).pack(side=tk.RIGHT, padx=5)
    
    def remove_plate(self):
        """Remove selected plate from blacklist"""
        selection = self.blacklist_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a plate to remove")
            return
        
        item = self.blacklist_tree.item(selection[0])
        plate_text = item['values'][0]
        
        result = messagebox.askyesno(
            "Confirm Removal", 
            f"Are you sure you want to remove '{plate_text}' from the blacklist?"
        )
        
        if result:
            if self.app.db.remove_from_blacklist(plate_text):
                messagebox.showinfo("Success", f"{plate_text} removed from blacklist")
                self.load_blacklist()  # Refresh the list
            else:
                messagebox.showerror("Error", "Failed to remove plate from blacklist")
    
    def import_blacklist(self):
        """Import blacklist from file"""
        from tkinter import filedialog
        import csv
        
        file_path = filedialog.askopenfilename(
            title="Import Blacklist",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            imported_data = []
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                # Try to detect delimiter
                sample = csvfile.read(1024)
                csvfile.seek(0)
                sniffer = csv.Sniffer()
                delimiter = sniffer.sniff(sample).delimiter
                
                reader = csv.reader(csvfile, delimiter=delimiter)
                header = next(reader, None)  # Skip header if exists
                
                for row in reader:
                    if len(row) >= 3:  # plate, reason, danger_level minimum
                        plate_text = row[0].strip().upper()
                        reason = row[1].strip()
                        danger_level = row[2].strip() if len(row) > 2 else "MEDIUM"
                        notes = row[3].strip() if len(row) > 3 else ""
                        
                        if plate_text and reason:
                            imported_data.append((plate_text, reason, danger_level, notes))
            
            if imported_data:
                count = self.app.db.import_blacklist_from_data(imported_data)
                messagebox.showinfo("Import Complete", f"Successfully imported {count} plates")
                self.load_blacklist()  # Refresh the list
            else:
                messagebox.showwarning("Warning", "No valid data found in file")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import file: {str(e)}")
    
    def export_blacklist(self):
        """Export blacklist to file"""
        from tkinter import filedialog
        import csv
        
        file_path = filedialog.asksaveasfilename(
            title="Export Blacklist",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            blacklist_data = self.app.db.get_all_blacklist()
            
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                # Write header
                writer.writerow(['Plate', 'Reason', 'Danger Level', 'Date Added', 'Notes'])
                
                # Write data
                for row in blacklist_data:
                    writer.writerow(row)
            
            messagebox.showinfo("Export Complete", f"Blacklist exported to {file_path}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export file: {str(e)}")


class StatisticsDialog:
    """Dialog for showing system statistics"""
    
    def __init__(self, parent, app):
        self.app = app
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("System Statistics")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        
        self.setup_ui()
        self.load_statistics()
    
    def setup_ui(self):
        """Setup dialog UI"""
        # Create notebook for different statistics views
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Today's statistics
        self.today_frame = ttk.Frame(notebook)
        notebook.add(self.today_frame, text="Today")
        self.setup_today_tab()
        
        # Historical statistics
        self.history_frame = ttk.Frame(notebook)
        notebook.add(self.history_frame, text="History")
        self.setup_history_tab()
        
        # System performance
        self.performance_frame = ttk.Frame(notebook)
        notebook.add(self.performance_frame, text="Performance")
        self.setup_performance_tab()
        
        # Close button
        ttk.Button(self.dialog, text="Close", command=self.dialog.destroy).pack(pady=10)
    
    def setup_today_tab(self):
        """Setup today's statistics tab"""
        self.today_text = scrolledtext.ScrolledText(self.today_frame, wrap=tk.WORD)
        self.today_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    def setup_history_tab(self):
        """Setup historical statistics tab"""
        # TODO: Add chart or graph for historical data
        self.history_text = scrolledtext.ScrolledText(self.history_frame, wrap=tk.WORD)
        self.history_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    def setup_performance_tab(self):
        """Setup performance statistics tab"""
        self.performance_text = scrolledtext.ScrolledText(self.performance_frame, wrap=tk.WORD)
        self.performance_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    def load_statistics(self):
        """Load and display statistics"""
        # Get today's statistics
        stats = self.app.db.get_statistics()
        if stats:
            self.display_today_stats(stats)
        
        # Get system performance data
        self.display_performance_stats()
    
    def display_today_stats(self, stats):
        """Display today's statistics"""
        # Calculate detection rate safely
        if stats['unique_plates'] > 0:
            detection_rate = f"{stats['total_detections'] / stats['unique_plates']:.1f} per plate"
        else:
            detection_rate = "N/A"

        text = f"""
Today's Statistics ({stats['date']})
{'=' * 40}

Total Detections: {stats['total_detections']}
Unique Plates: {stats['unique_plates']}
Suspicious Events: {stats['suspicious_events']}
Blacklist Hits: {stats['blacklist_hits']}

Average Detections per Hour: {stats['total_detections'] / 24:.1f}
Detection Rate: {detection_rate}
"""
        
        self.today_text.delete('1.0', tk.END)
        self.today_text.insert('1.0', text)
        self.today_text.config(state='disabled')
    
    def display_performance_stats(self):
        """Display performance statistics"""
        # TODO: Get actual performance data
        text = """
System Performance
{'=' * 40}

Processing FPS: N/A
Queue Size: N/A
Memory Usage: N/A
CPU Usage: N/A
Disk Usage: N/A
"""
        
        self.performance_text.delete('1.0', tk.END)
        self.performance_text.insert('1.0', text)
        self.performance_text.config(state='disabled')


class ExportDialog:
    """Dialog for exporting data"""
    
    def __init__(self, parent, app):
        self.app = app
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Export Data")
        self.dialog.geometry("400x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup dialog UI"""
        # Export type
        ttk.Label(self.dialog, text="Export Type:").pack(anchor=tk.W, padx=10, pady=5)
        self.export_type = tk.StringVar(value="csv")
        ttk.Radiobutton(self.dialog, text="CSV", variable=self.export_type, value="csv").pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(self.dialog, text="JSON", variable=self.export_type, value="json").pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(self.dialog, text="Excel", variable=self.export_type, value="excel").pack(anchor=tk.W, padx=20)
        
        # Date range
        ttk.Label(self.dialog, text="Date Range:").pack(anchor=tk.W, padx=10, pady=(20, 5))
        self.date_range = tk.StringVar(value="today")
        ttk.Radiobutton(self.dialog, text="Today", variable=self.date_range, value="today").pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(self.dialog, text="Last 7 days", variable=self.date_range, value="week").pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(self.dialog, text="Last 30 days", variable=self.date_range, value="month").pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(self.dialog, text="All data", variable=self.date_range, value="all").pack(anchor=tk.W, padx=20)
        
        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=20)
        
        ttk.Button(button_frame, text="Export", command=self.export_data).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
    def export_data(self):
        """Export data based on selected options"""
        export_type = self.export_type.get()
        date_range = self.date_range.get()
        
        # Ask for file location
        if export_type == "csv":
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
        elif export_type == "json":
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
        else:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
            )
        
        if file_path:
            # TODO: Implement actual export based on date range
            count = self.app.db.export_data(file_path)
            messagebox.showinfo("Export Complete", f"Exported {count} records to {file_path}")
            self.dialog.destroy()


class PlateImagesDialog:
    """Dialog for viewing plate images"""
    
    def __init__(self, parent, app, plate_text):
        self.app = app
        self.plate_text = plate_text
        self.current_image_index = 0
        self.images = []
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Images: {plate_text}")
        self.dialog.geometry("800x600")
        self.dialog.transient(parent)
        
        self.setup_ui()
        self.load_images()
    
    def setup_ui(self):
        """Setup dialog UI"""
        # Image display
        self.image_label = ttk.Label(self.dialog)
        self.image_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Navigation buttons
        nav_frame = ttk.Frame(self.dialog)
        nav_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(nav_frame, text="Previous", command=self.previous_image).pack(side=tk.LEFT, padx=5)
        self.image_info_label = ttk.Label(nav_frame, text="")
        self.image_info_label.pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(nav_frame, text="Next", command=self.next_image).pack(side=tk.RIGHT, padx=5)
        
        # Close button
        ttk.Button(self.dialog, text="Close", command=self.dialog.destroy).pack(pady=10)
    
    def load_images(self):
        """Load available images for the plate"""
        # TODO: Implement image loading from detection directory
        pass
    
    def display_image(self, index):
        """Display image at given index"""
        if not self.images or index >= len(self.images):
            return
        
        # TODO: Display the image
        self.image_info_label.config(text=f"Image {index + 1} of {len(self.images)}")
    
    def previous_image(self):
        """Show previous image"""
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self.display_image(self.current_image_index)
    
    def next_image(self):
        """Show next image"""
        if self.current_image_index < len(self.images) - 1:
            self.current_image_index += 1
            self.display_image(self.current_image_index)