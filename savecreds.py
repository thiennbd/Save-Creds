# -*- coding: utf-8 -*-
from burp import IBurpExtender
from burp import IContextMenuFactory
from burp import ITab
from burp import IExtensionStateListener
from javax.swing import (
    JPanel, JButton, JScrollPane, JLabel, JMenuItem,
    JCheckBox, JTextField, JTextArea, JFileChooser, BorderFactory, Box, BoxLayout, SwingUtilities, JWindow
)
from java.awt import BorderLayout, FlowLayout, Toolkit, Color, Dimension, Cursor
import time
from java.awt.event import MouseListener, MouseMotionListener
from java.awt.datatransfer import StringSelection
from java.lang import Runnable
from java.util import ArrayList
import os
import threading
import codecs
import json
from javax.swing import Scrollable, JOptionPane
from javax.swing.event import DocumentListener
from java.awt import FileDialog, Frame

class ScrollablePanel(JPanel, Scrollable):
    def getPreferredScrollableViewportSize(self):
        return self.getPreferredSize()
    def getScrollableUnitIncrement(self, visibleRect, orientation, direction):
        return 16
    def getScrollableBlockIncrement(self, visibleRect, orientation, direction):
        return 16
    def getScrollableTracksViewportWidth(self):
        return True
    def getScrollableTracksViewportHeight(self):
        return False

class ToastManager:
    _toast = None
    _lbl = None
    _hide_time = 0
    _thread_running = False

    @classmethod
    def show(cls, message, anchor_component=None, delay_ms=800):
        class ShowRunnable(Runnable):
            def run(self):
                if not cls._toast:
                    cls._toast = JWindow()
                    cls._toast.setLayout(BorderLayout())
                    
                    cls._lbl = JLabel(message)
                    cls._lbl.setForeground(Color.WHITE)
                    cls._lbl.setBorder(BorderFactory.createEmptyBorder(10, 20, 10, 20))
                    
                    panel = JPanel(BorderLayout())
                    panel.setBackground(Color.DARK_GRAY)
                    panel.setBorder(BorderFactory.createLineBorder(Color.GRAY, 1))
                    panel.add(cls._lbl, BorderLayout.CENTER)
                    
                    cls._toast.add(panel)
                    cls._toast.setAlwaysOnTop(True)
                
                cls._lbl.setText(message)
                cls._toast.pack()
                
                try:
                    if anchor_component and anchor_component.isVisible() and anchor_component.isShowing():
                        pt = anchor_component.getLocationOnScreen()
                        x = pt.x + (anchor_component.getWidth() - cls._toast.getWidth()) / 2
                        y = pt.y + anchor_component.getHeight() - 100
                    else:
                        dim = Toolkit.getDefaultToolkit().getScreenSize()
                        x = (dim.width - cls._toast.getWidth()) / 2
                        y = dim.height - 150
                    cls._toast.setLocation(x, y)
                except Exception:
                    pass
                
                cls._toast.setVisible(True)
                cls._hide_time = time.time() + (delay_ms / 1000.0)
                
                if not cls._thread_running:
                    cls._thread_running = True
                    def close_toast():
                        while True:
                            now = time.time()
                            if now >= cls._hide_time:
                                break
                            try:
                                time.sleep(cls._hide_time - now)
                            except Exception:
                                pass
                        
                        class CloseRunnable(Runnable):
                            def run(self):
                                if cls._toast:
                                    cls._toast.setVisible(False)
                        SwingUtilities.invokeLater(CloseRunnable())
                        cls._thread_running = False
                    
                    threading.Thread(target=close_toast).start()
        
        SwingUtilities.invokeLater(ShowRunnable())

class BlockPanel(JPanel):
    def getMaximumSize(self):
        size = self.getPreferredSize()
        size.width = 32767
        return size

class DragListener(MouseListener, MouseMotionListener):
    def __init__(self, block, extender):
        self.block = block
        self.extender = extender
        self.start_y = 0
        
    def mousePressed(self, e):
        # Convert click coordinates to blocks_container space
        p = SwingUtilities.convertPoint(e.getComponent(), e.getPoint(), self.extender.blocks_container)
        self.start_y = p.y
        e.getComponent().setCursor(Cursor.getPredefinedCursor(Cursor.MOVE_CURSOR))
        
    def mouseDragged(self, e):
        # Convert drag coordinates to blocks_container space
        p = SwingUtilities.convertPoint(e.getComponent(), e.getPoint(), self.extender.blocks_container)
        delta_y = p.y - self.start_y
        
        card_height = self.block.panel.getHeight()
        if card_height <= 0:
            card_height = 80 # Fallback default height
            
        try:
            idx = self.extender.blocks.index(self.block)
        except ValueError:
            return
            
        # If dragged up past half card height
        if delta_y < -card_height / 2:
            if idx > 0:
                # Swap elements in memory
                self.extender.blocks[idx], self.extender.blocks[idx - 1] = self.extender.blocks[idx - 1], self.extender.blocks[idx]
                self.extender.rebuild_ui()
                self.start_y -= card_height
        # If dragged down past half card height
        elif delta_y > card_height / 2:
            if idx < len(self.extender.blocks) - 1:
                # Swap elements in memory
                self.extender.blocks[idx], self.extender.blocks[idx + 1] = self.extender.blocks[idx + 1], self.extender.blocks[idx]
                self.extender.rebuild_ui()
                self.start_y += card_height
                
    def mouseReleased(self, e):
        e.getComponent().setCursor(Cursor.getPredefinedCursor(Cursor.HAND_CURSOR))
        
    def mouseClicked(self, e): pass
    def mouseEntered(self, e): pass
    def mouseExited(self, e): pass
    def mouseMoved(self, e): pass

class CookieBlock(object):
    def __init__(self, token_val, default_title, extender, remove_callback):
        self.token_val = token_val
        self.extender = extender
        self.remove_callback = remove_callback
        
        # Block card panel
        self.panel = BlockPanel(BorderLayout(5, 5))
        # Custom card border with padding
        self.panel.setBorder(BorderFactory.createCompoundBorder(
            BorderFactory.createEmptyBorder(5, 10, 5, 10),
            BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(Color(200, 200, 200), 1),
                BorderFactory.createEmptyBorder(10, 10, 10, 10)
            )
        ))
        
        # Checkbox to select/deselect for copy/export
        self.checkbox = JCheckBox("", True)
        
        # Drag handle (Using ASCII "::" to prevent font rendering issue)
        self.lbl_drag = JLabel("::")
        self.lbl_drag.setForeground(Color(120, 120, 120))
        self.lbl_drag.setFont(self.lbl_drag.getFont().deriveFont(14.0))
        self.lbl_drag.setCursor(Cursor.getPredefinedCursor(Cursor.HAND_CURSOR))
        self.lbl_drag.setToolTipText("Drag here to reorder this block")
        
        # Register drag listeners
        drag_listener = DragListener(self, extender)
        self.lbl_drag.addMouseListener(drag_listener)
        self.lbl_drag.addMouseMotionListener(drag_listener)
        
        # Left Panel (Drag Handle + Checkbox)
        left_panel = JPanel(FlowLayout(FlowLayout.LEFT, 5, 0))
        left_panel.setOpaque(False)
        left_panel.add(self.lbl_drag)
        left_panel.add(self.checkbox)
        
        # Middle panel containing Title (Row 1) and Cookie/Token (Row 2)
        mid_panel = JPanel()
        mid_panel.setLayout(BoxLayout(mid_panel, BoxLayout.Y_AXIS))
        mid_panel.setBorder(BorderFactory.createEmptyBorder(0, 5, 0, 10))
        
        # Set alignment sizes for labels
        label_size = Dimension(55, 20)
        
        # Row 1: Title (Editable by user to set identifier/note)
        row1 = JPanel(BorderLayout(5, 5))
        lbl_title = JLabel("Title: ")
        lbl_title.setPreferredSize(label_size)
        self.txt_title = JTextField(default_title)
        row1.add(lbl_title, BorderLayout.WEST)
        row1.add(self.txt_title, BorderLayout.CENTER)
        
        # Row 2: Cookie Value (Editable, word wrap enabled to fit long strings inside window)
        row2 = JPanel(BorderLayout(5, 5))
        lbl_val = JLabel("Cookie: ")
        lbl_val.setPreferredSize(label_size)
        
        self.txt_value = JTextArea(2, 30)
        self.txt_value.setText(token_val)
        self.txt_value.setLineWrap(True)
        self.txt_value.setWrapStyleWord(True)
        
        # Style JTextArea to match a JTextField look-and-feel
        dummy = JTextField()
        self.txt_value.setFont(dummy.getFont())
        self.txt_value.setBorder(dummy.getBorder())
        self.txt_value.setBackground(dummy.getBackground())
        self.txt_value.setCaretColor(dummy.getCaretColor())
        
        row2.add(lbl_val, BorderLayout.WEST)
        row2.add(self.txt_value, BorderLayout.CENTER)
        
        mid_panel.add(row1)
        mid_panel.add(Box.createVerticalStrut(5))
        mid_panel.add(row2)
        
        # Right panel: Actions
        right_panel = JPanel()
        right_panel.setLayout(BoxLayout(right_panel, BoxLayout.Y_AXIS))
        
        btn_copy = JButton("Copy", actionPerformed=self.copy_cookie)
        btn_clear = JButton("Clear", actionPerformed=self.clear_cookie)
        btn_delete = JButton("Delete", actionPerformed=self.delete_block)
        
        btn_dim = Dimension(75, 25)
        btn_copy.setMaximumSize(btn_dim)
        btn_clear.setMaximumSize(btn_dim)
        btn_delete.setMaximumSize(btn_dim)
        
        right_panel.add(btn_copy)
        right_panel.add(Box.createVerticalStrut(5))
        right_panel.add(btn_clear)
        right_panel.add(Box.createVerticalStrut(5))
        right_panel.add(btn_delete)
        
        # Assemble components in the block card
        self.panel.add(left_panel, BorderLayout.WEST)
        self.panel.add(mid_panel, BorderLayout.CENTER)
        self.panel.add(right_panel, BorderLayout.EAST)
        
    def copy_cookie(self, event):
        text = self.txt_value.getText().strip()
        if text:
            try:
                selection = StringSelection(text)
                clipboard = Toolkit.getDefaultToolkit().getSystemClipboard()
                clipboard.setContents(selection, None)
                ToastManager.show("Cookie copied to clipboard!", self.panel, 800)
            except Exception as e:
                pass

    def clear_cookie(self, event):
        self.txt_value.setText("")

    def delete_block(self, event):
        self.remove_callback(self)

class BurpExtender(IBurpExtender, IContextMenuFactory, ITab, IExtensionStateListener):
    
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        
        # Set Extension name
        callbacks.setExtensionName("Save Creds")
        
        # List to store CookieBlock instances
        self.blocks = []
        
        # Initialize User Interface
        self.initUI()
        
        # Load persisted data
        self.load_data()
        
        # Register interfaces
        callbacks.registerContextMenuFactory(self)
        callbacks.registerExtensionStateListener(self)
        
        # Add Tab to Burp Suite
        callbacks.addSuiteTab(self)
        print("[-] Save Creds extension loaded successfully!")
        
    def extensionUnloaded(self):
        self.save_data()
        
    def save_data(self):
        try:
            data = []
            for block in self.blocks:
                data.append({
                    "title": block.txt_title.getText(),
                    "value": block.txt_value.getText()
                })
            json_str = json.dumps(data)
            self._callbacks.saveExtensionSetting("SaveCredsData", json_str)
        except Exception as e:
            print("[-] Error saving data: " + str(e))
            
    def load_data(self):
        try:
            json_str = self._callbacks.loadExtensionSetting("SaveCredsData")
            if json_str:
                data = json.loads(json_str)
                for item in data:
                    self.add_block(item.get("value", ""), title=item.get("title", ""))
        except Exception as e:
            print("[-] Error loading data: " + str(e))

    def initUI(self):
        # Main container panel
        self.panel = JPanel(BorderLayout())
        
        # Search panel
        search_panel = JPanel(BorderLayout(5, 5))
        search_panel.setBorder(BorderFactory.createEmptyBorder(5, 5, 5, 5))
        search_panel.add(JLabel("Search: "), BorderLayout.WEST)
        self.txt_search = JTextField()
        
        class SearchListener(DocumentListener):
            def __init__(self, extender):
                self.extender = extender
            def insertUpdate(self, e): self.extender.filter_blocks()
            def removeUpdate(self, e): self.extender.filter_blocks()
            def changedUpdate(self, e): self.extender.filter_blocks()
            
        self.txt_search.getDocument().addDocumentListener(SearchListener(self))
        search_panel.add(self.txt_search, BorderLayout.CENTER)
        
        self.panel.add(search_panel, BorderLayout.NORTH)
        
        # Vertical box panel for blocks
        self.blocks_container = JPanel()
        self.blocks_container.setLayout(BoxLayout(self.blocks_container, BoxLayout.Y_AXIS))
        
        # Wrapper panel to align blocks at the top
        inner_panel = ScrollablePanel(BorderLayout())
        inner_panel.add(self.blocks_container, BorderLayout.NORTH)
        
        scroll_pane = JScrollPane(inner_panel)
        scroll_pane.getVerticalScrollBar().setUnitIncrement(16)
        
        # Action control panel at the bottom
        control_panel = JPanel(BorderLayout(5, 5))
        control_panel.setBorder(BorderFactory.createEmptyBorder(5, 5, 5, 5))
        
        btn_panel = JPanel(FlowLayout(FlowLayout.LEFT, 5, 0))
        
        self.chk_tick_all = JCheckBox("Select All", True)
        self.chk_tick_all.addActionListener(self.toggle_tick_all)
        
        btn_copy = JButton("Copy to Clipboard", actionPerformed=self.copy_to_clipboard)
        btn_export = JButton("Export Wordlist", actionPerformed=self.export_wordlist)
        btn_import = JButton("Import Titles", actionPerformed=self.import_titles)
        btn_clear_val = JButton("Clear Values", actionPerformed=self.clear_all_values)
        btn_clear = JButton("Clear Blocks", actionPerformed=self.clear_data)
        
        btn_panel.add(self.chk_tick_all)
        btn_panel.add(btn_copy)
        btn_panel.add(btn_export)
        btn_panel.add(btn_import)
        btn_panel.add(btn_clear_val)
        btn_panel.add(btn_clear)
        
        count_panel = JPanel(FlowLayout(FlowLayout.RIGHT, 5, 0))
        self.lbl_count = JLabel("Total: 0")
        self.lbl_count.setFont(self.lbl_count.getFont().deriveFont(12.0))
        count_panel.add(self.lbl_count)
        
        control_panel.add(btn_panel, BorderLayout.WEST)
        control_panel.add(count_panel, BorderLayout.EAST)
        
        self.panel.add(scroll_pane, BorderLayout.CENTER)
        self.panel.add(control_panel, BorderLayout.SOUTH)

    # Context Menu MenuItems generator
    def createMenuItems(self, invocation):
        menu_list = ArrayList()
        selection_bounds = invocation.getSelectionBounds()
        
        # Only show context menu item if user selected text
        if selection_bounds is not None and selection_bounds[0] != selection_bounds[1]:
            menu_item = JMenuItem("Send to Save Creds (New)", actionPerformed=lambda x: self.add_selected_text(invocation))
            menu_list.add(menu_item)
            
            if self.blocks:
                # Add separator
                menu_list.add(JMenuItem("------ Replace Existing ------"))
                menu_list.get(menu_list.size() - 1).setEnabled(False)
                
                for block in self.blocks:
                    title = block.txt_title.getText().strip()
                    if not title:
                        title = "Untitled"
                    
                    item = JMenuItem("Replace in: " + title, actionPerformed=lambda x, b=block: self.replace_selected_text(invocation, b))
                    menu_list.add(item)
            
        return menu_list

    # Handle click on context menu item
    def add_selected_text(self, invocation):
        messages = invocation.getSelectedMessages()
        if not messages:
            return
            
        bounds = invocation.getSelectionBounds()
        
        if invocation.getInvocationContext() in [invocation.CONTEXT_MESSAGE_EDITOR_REQUEST, invocation.CONTEXT_MESSAGE_VIEWER_REQUEST]:
            data = messages[0].getRequest()
        else:
            data = messages[0].getResponse()
            
        if data is None:
            return
            
        try:
            # Extract highlighted selection
            selected_bytes = data[bounds[0]:bounds[1]]
            selected_text = self._helpers.bytesToString(selected_bytes).strip()
            
            if selected_text:
                class SwingRunnable(Runnable):
                    def __init__(self, extender, text):
                        self.extender = extender
                        self.text = text
                    def run(self):
                        self.extender.add_block(self.text)
                
                SwingUtilities.invokeLater(SwingRunnable(self, selected_text))
                print("[+] Added: " + selected_text)
        except Exception as e:
            print("[-] Error extracting string: " + str(e))

    def replace_selected_text(self, invocation, block):
        messages = invocation.getSelectedMessages()
        if not messages:
            return
            
        bounds = invocation.getSelectionBounds()
        
        if invocation.getInvocationContext() in [invocation.CONTEXT_MESSAGE_EDITOR_REQUEST, invocation.CONTEXT_MESSAGE_VIEWER_REQUEST]:
            data = messages[0].getRequest()
        else:
            data = messages[0].getResponse()
            
        if data is None:
            return
            
        try:
            selected_bytes = data[bounds[0]:bounds[1]]
            selected_text = self._helpers.bytesToString(selected_bytes).strip()
            
            if selected_text:
                class SwingRunnable(Runnable):
                    def __init__(self, b, text):
                        self.b = b
                        self.text = text
                    def run(self):
                        self.b.txt_value.setText(self.text)
                
                SwingUtilities.invokeLater(SwingRunnable(block, selected_text))
                print("[+] Replaced value in block: " + block.txt_title.getText())
        except Exception as e:
            print("[-] Error replacing string: " + str(e))

    def filter_blocks(self):
        query = self.txt_search.getText().lower()
        for block in self.blocks:
            title = block.txt_title.getText().lower()
            val = block.txt_value.getText().lower()
            if query in title or query in val:
                block.panel.setVisible(True)
            else:
                block.panel.setVisible(False)
        self.blocks_container.revalidate()
        self.blocks_container.repaint()

    def add_block(self, token_val, title=None):
        if title is None:
            index = len(self.blocks) + 1
            default_title = "Cookie/Token #" + str(index)
        else:
            default_title = title
        
        # Instantiate new block card
        block = CookieBlock(token_val, default_title, self, self.remove_block)
        self.blocks.append(block)
        
        # Add to UI container
        self.blocks_container.add(block.panel)
        
        # Refresh container layout
        self.blocks_container.revalidate()
        self.blocks_container.repaint()
        
        # Update UI count label
        self.update_count()

    def remove_block(self, block):
        if block in self.blocks:
            self.blocks.remove(block)
            self.blocks_container.remove(block.panel)
            self.blocks_container.revalidate()
            self.blocks_container.repaint()
            self.update_count()

    def rebuild_ui(self):
        class SwingRunnable(Runnable):
            def __init__(self, extender):
                self.extender = extender
            def run(self):
                self.extender.blocks_container.removeAll()
                for b in self.extender.blocks:
                    self.extender.blocks_container.add(b.panel)
                self.extender.blocks_container.revalidate()
                self.extender.blocks_container.repaint()
                
        SwingUtilities.invokeLater(SwingRunnable(self))

    def update_count(self):
        self.lbl_count.setText("Total: " + str(len(self.blocks)))

    def clear_data(self, event):
        self.blocks = []
        self.blocks_container.removeAll()
        self.blocks_container.revalidate()
        self.blocks_container.repaint()
        self.update_count()

    def toggle_tick_all(self, event):
        state = self.chk_tick_all.isSelected()
        for block in self.blocks:
            block.checkbox.setSelected(state)

    def clear_all_values(self, event):
        for block in self.blocks:
            block.txt_value.setText("")

    def get_selected_values(self):
        values = []
        for block in self.blocks:
            if block.checkbox.isSelected():
                val = block.txt_value.getText().strip()
                if val:
                    values.append(val)
        return values

    def copy_to_clipboard(self, event):
        values = self.get_selected_values()
        if not values:
            return
        
        text = "\n".join(values)
        try:
            selection = StringSelection(text)
            clipboard = Toolkit.getDefaultToolkit().getSystemClipboard()
            clipboard.setContents(selection, None)
            msg = "Copied " + str(len(values)) + " items to Clipboard!"
            print("[+] " + msg)
            ToastManager.show(msg, self.panel, 800)
        except Exception as e:
            print("[-] Error copying to clipboard: " + str(e))

    def export_wordlist(self, event):
        values = self.get_selected_values()
        if not values:
            return
        
        # Retrieve parent window to keep modal parenting clean
        parent_window = SwingUtilities.getWindowAncestor(self.panel)
        if parent_window is None:
            parent_window = Frame()
            
        # Use native OS FileDialog for lag-free experience
        fd = FileDialog(parent_window, "Save Wordlist", FileDialog.SAVE)
        fd.setFile("wordlist.txt")
        fd.setVisible(True)
        
        file_dir = fd.getDirectory()
        file_name = fd.getFile()
        
        if file_dir and file_name:
            if not file_name.endswith(".txt"):
                file_name += ".txt"
            file_path = os.path.join(file_dir, file_name)
            
            # Write file in background thread to avoid UI lag/freeze
            def do_write():
                try:
                    with codecs.open(file_path, "w", "utf-8") as f:
                        for item in values:
                            f.write(item + u"\n")
                    print("[+] Wordlist exported successfully to: " + file_path)
                except Exception as e:
                    print("[-] Error saving file: " + str(e))
            
            threading.Thread(target=do_write).start()

    def import_titles(self, event):
        parent_window = SwingUtilities.getWindowAncestor(self.panel)
        if parent_window is None:
            parent_window = Frame()
            
        fd = FileDialog(parent_window, "Import Titles Wordlist", FileDialog.LOAD)
        fd.setVisible(True)
        
        file_dir = fd.getDirectory()
        file_name = fd.getFile()
        
        if file_dir and file_name:
            file_path = os.path.join(file_dir, file_name)
            
            def do_import():
                try:
                    with codecs.open(file_path, "r", "utf-8-sig") as f:
                        lines = f.readlines()
                    
                    count = 0
                    for line in lines:
                        line = line.strip()
                        if line:
                            class SwingRunnable(Runnable):
                                def __init__(self, ext, t):
                                    self.ext = ext
                                    self.t = t
                                def run(self):
                                    self.ext.add_block("", title=self.t)
                            SwingUtilities.invokeLater(SwingRunnable(self, line))
                            count += 1
                    print("[+] Imported " + str(count) + " titles from: " + file_path)
                except Exception as e:
                    print("[-] Error importing titles: " + str(e))
            
            threading.Thread(target=do_import).start()

    # Required ITab interfaces
    def getTabCaption(self):
        return "Save Creds"
        
    def getUiComponent(self):
        return self.panel