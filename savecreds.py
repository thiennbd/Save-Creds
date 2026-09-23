# -*- coding: utf-8 -*-
from burp import IBurpExtender
from burp import IContextMenuFactory
from burp import ITab
from burp import IExtensionStateListener
from javax.swing import (
    JPanel, JButton, JScrollPane, JLabel, JMenuItem, JMenu,
    JCheckBox, JTextField, JTextArea, JFileChooser, BorderFactory, Box, BoxLayout, SwingUtilities, JWindow,
    DefaultListModel, JList, ListSelectionModel, Timer, JSplitPane
)
from java.awt import BorderLayout, FlowLayout, Toolkit, Color, Dimension, Cursor, Rectangle
import time
from java.awt.event import MouseListener, MouseMotionListener, ComponentAdapter
from java.awt.datatransfer import StringSelection
from java.lang import Runnable
from java.util import ArrayList
import os
import threading
import codecs
import json
from javax.swing import Scrollable, JOptionPane, AbstractAction, KeyStroke, JComponent
from javax.swing.undo import UndoManager, CannotUndoException, CannotRedoException
from java.awt.event import KeyEvent, InputEvent, FocusListener
from java.awt import Insets
from javax.swing.event import DocumentListener, ListSelectionListener
from java.awt import Frame
from java.io import File

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

class UndoRedoAction(AbstractAction):
    def __init__(self, manager, is_undo):
        AbstractAction.__init__(self)
        self.manager = manager
        self.is_undo = is_undo
    def actionPerformed(self, e):
        try:
            if self.is_undo and self.manager.canUndo():
                self.manager.undo()
            elif not self.is_undo and self.manager.canRedo():
                self.manager.redo()
        except (CannotUndoException, CannotRedoException):
            pass

def enable_undo(field):
    # Call after the initial text is set so the initial value isn't undoable
    manager = UndoManager()
    manager.setLimit(200)
    field.getDocument().addUndoableEditListener(manager)

    ctrl = InputEvent.CTRL_DOWN_MASK
    input_map = field.getInputMap(JComponent.WHEN_FOCUSED)
    action_map = field.getActionMap()
    input_map.put(KeyStroke.getKeyStroke(KeyEvent.VK_Z, ctrl), "savecreds-undo")
    input_map.put(KeyStroke.getKeyStroke(KeyEvent.VK_Y, ctrl), "savecreds-redo")
    input_map.put(KeyStroke.getKeyStroke(KeyEvent.VK_Z, ctrl | InputEvent.SHIFT_DOWN_MASK), "savecreds-redo")
    action_map.put("savecreds-undo", UndoRedoAction(manager, True))
    action_map.put("savecreds-redo", UndoRedoAction(manager, False))

class BlockFocusListener(FocusListener):
    # Focusing a title/cookie field highlights its whole block, same as picking it from the titles list
    def __init__(self, block, extender):
        self.block = block
        self.extender = extender
    def focusGained(self, e):
        self.extender.select_block(self.block, scroll=False)
    def focusLost(self, e):
        pass

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

class TitleChangeListener(DocumentListener):
    def __init__(self, extender):
        self.extender = extender
    # Never touch other components inside a document event: it breaks IME composition (e.g. Vietnamese)
    def _changed(self):
        try:
            self.extender.request_nav_update()
            self.extender.schedule_save()
        except Exception:
            pass
    def insertUpdate(self, e): self._changed()
    def removeUpdate(self, e): self._changed()
    def changedUpdate(self, e): self._changed()

class ValueChangeListener(DocumentListener):
    def __init__(self, extender):
        self.extender = extender
    def _changed(self):
        try:
            self.extender.schedule_save()
        except Exception:
            pass
    def insertUpdate(self, e): self._changed()
    def removeUpdate(self, e): self._changed()
    def changedUpdate(self, e): self._changed()

class NavSelectListener(ListSelectionListener):
    def __init__(self, extender):
        self.extender = extender
    def valueChanged(self, event):
        if event.getValueIsAdjusting() or self.extender._nav_updating:
            return
        idx = self.extender.nav_list.getSelectedIndex()
        if 0 <= idx < len(self.extender.blocks):
            self.extender.select_block(self.extender.blocks[idx])

class InitialDividerListener(ComponentAdapter):
    # Give the titles list a sensible width once, when the split pane first gets a real size
    def __init__(self, split_pane, right_width):
        self.split_pane = split_pane
        self.right_width = right_width
        self.done = False
    def componentResized(self, e):
        if self.done or self.split_pane.getWidth() <= 0:
            return
        self.done = True
        self.split_pane.setDividerLocation(self.split_pane.getWidth() - self.right_width - self.split_pane.getDividerSize())

class NavClickListener(MouseListener):
    # Re-clicking the already selected title doesn't fire a selection event
    def __init__(self, extender):
        self.extender = extender
    def mousePressed(self, e):
        lst = self.extender.nav_list
        idx = lst.locationToIndex(e.getPoint())
        if idx >= 0 and lst.getCellBounds(idx, idx).contains(e.getPoint()) and idx < len(self.extender.blocks):
            self.extender.select_block(self.extender.blocks[idx])
    def mouseReleased(self, e): pass
    def mouseClicked(self, e): pass
    def mouseEntered(self, e): pass
    def mouseExited(self, e): pass

class CookieBlock(object):
    def __init__(self, token_val, default_title, extender, remove_callback):
        self.token_val = token_val
        self.extender = extender
        self.remove_callback = remove_callback
        
        # Block card panel
        self.panel = BlockPanel(BorderLayout(5, 5))
        # Custom card border with padding
        self.default_border = BorderFactory.createCompoundBorder(
            BorderFactory.createEmptyBorder(5, 10, 5, 10),
            BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(Color(200, 200, 200), 1),
                BorderFactory.createEmptyBorder(10, 10, 10, 10)
            )
        )
        # Same overall thickness as default_border, but with a thicker colored line
        # so the highlight flash doesn't shift the layout
        self.highlight_border = BorderFactory.createCompoundBorder(
            BorderFactory.createEmptyBorder(5, 10, 5, 10),
            BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(Color(255, 140, 0), 3),
                BorderFactory.createEmptyBorder(8, 8, 8, 8)
            )
        )
        self.panel.setBorder(self.default_border)

        # Checkbox to select/deselect for copy/export
        self.checkbox = JCheckBox("", True)
        self.checkbox.addActionListener(self.on_checkbox_changed)

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
        self.txt_title.getDocument().addDocumentListener(TitleChangeListener(extender))
        row1.add(lbl_title, BorderLayout.WEST)
        row1.add(self.txt_title, BorderLayout.CENTER)
        
        # Row 2: Cookie Value (Editable, word wrap enabled to fit long strings inside window)
        row2 = JPanel(BorderLayout(5, 5))
        lbl_val = JLabel("Cookie: ")
        lbl_val.setPreferredSize(label_size)
        
        self.txt_value = JTextArea(2, 30)
        self.txt_value.setText(token_val)
        self.txt_value.getDocument().addDocumentListener(ValueChangeListener(extender))
        self.txt_value.setLineWrap(True)
        self.txt_value.setWrapStyleWord(True)
        
        # Style JTextArea to match a JTextField look-and-feel
        dummy = JTextField()
        self.txt_value.setFont(dummy.getFont())
        self.txt_value.setBorder(dummy.getBorder())
        self.txt_value.setBackground(dummy.getBackground())
        self.txt_value.setCaretColor(dummy.getCaretColor())
        
        for field in (self.txt_title, self.txt_value):
            field.setEditable(True)
            field.setEnabled(True)
            field.setFocusable(True)
            field.enableInputMethods(True)
            enable_undo(field)
            field.addFocusListener(BlockFocusListener(self, extender))

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
        btn_delete = JButton("Remove", actionPerformed=self.delete_block)
        
        btn_dim = Dimension(100, 25)
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

    def on_checkbox_changed(self, event):
        self.extender.update_select_all()

    def clear_cookie(self, event):
        self.txt_value.setText("")

    def delete_block(self, event):
        self.remove_callback(self)

    def set_highlight(self, on):
        self.panel.setBorder(self.highlight_border if on else self.default_border)
        self.panel.revalidate()
        self.panel.repaint()

class BurpExtender(IBurpExtender, IContextMenuFactory, ITab, IExtensionStateListener):
    
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        
        # Set Extension name
        callbacks.setExtensionName("Save Creds")
        
        # List to store CookieBlock instances
        self.blocks = []
        self._proj_id = None
        self._save_timer = None
        self._loading = False
        self._nav_updating = False
        self._nav_refresh_pending = False
        self.active_block = None

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

    def get_project_id(self):
        for f in Frame.getFrames():
            title = f.getTitle()
            if f.isVisible() and "Burp Suite" in title:
                if " - " in title:
                    proj_name = title.split(" - ", 1)[-1].strip()
                    if "Temporary Project" in proj_name:
                        proj_name = "temporary"
                    self._proj_id = proj_name
                    return proj_name
        # Burp window may be gone during unload/shutdown: reuse the last known id
        return self._proj_id or "default"

    def schedule_save(self):
        if self._save_timer is not None:
            self._save_timer.stop()
        self._save_timer = Timer(1000, actionPerformed=lambda e: self.save_data())
        self._save_timer.setRepeats(False)
        self._save_timer.start()

    def save_data(self):
        if self._loading:
            return
        proj_id = self.get_project_id()

        try:
            data = []
            for block in self.blocks:
                data.append({
                    "title": block.txt_title.getText(),
                    "value": block.txt_value.getText()
                })
            json_str = json.dumps(data)
            self._callbacks.saveExtensionSetting("SaveCredsData_" + proj_id, json_str)
        except Exception as e:
            print("[-] Error saving data: " + str(e))
            
    def load_data(self):
        proj_id = self.get_project_id()

        try:
            json_str = self._callbacks.loadExtensionSetting("SaveCredsData_" + proj_id)
            if not json_str and proj_id != "default":
                json_str = self._callbacks.loadExtensionSetting("SaveCredsData_default")
            data = json.loads(json_str) if json_str else []
        except Exception as e:
            print("[-] Error loading data: " + str(e))
            return

        class LoadRunnable(Runnable):
            def __init__(self, extender, items):
                self.extender = extender
                self.items = items
            def run(self):
                ext = self.extender
                ext._loading = True
                loaded = 0
                try:
                    for item in self.items:
                        try:
                            ext.add_block(item.get("value", ""), title=item.get("title", ""))
                            loaded += 1
                        except Exception as e:
                            print("[-] Error loading block: " + str(e))
                finally:
                    ext._loading = False
                print("[+] Loaded " + str(loaded) + "/" + str(len(self.items)) + " blocks")

        # Swing components must be built on the EDT; wait so blocks exist before the tab is added
        if SwingUtilities.isEventDispatchThread():
            LoadRunnable(self, data).run()
        else:
            SwingUtilities.invokeAndWait(LoadRunnable(self, data))

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
        enable_undo(self.txt_search)
        search_panel.add(self.txt_search, BorderLayout.CENTER)
        
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
        
        self.chk_tick_all = JCheckBox("Select All", False)
        self.chk_tick_all.addActionListener(self.toggle_tick_all)
        
        btn_new = JButton("New Title", actionPerformed=self.new_title)
        btn_copy = JButton("Copy to Clipboard", actionPerformed=self.copy_to_clipboard)
        btn_export = JButton("Export Wordlist", actionPerformed=self.export_wordlist)
        btn_import = JButton("Import", actionPerformed=self.import_data)
        btn_clear_val = JButton("Clear Values", actionPerformed=self.clear_all_values)
        btn_clear = JButton("Remove All", actionPerformed=self.clear_data)
        
        btn_panel.add(self.chk_tick_all)
        btn_panel.add(btn_new)
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
        
        # Right-side navigation panel: list of all titles for quick jump
        nav_panel = JPanel(BorderLayout(5, 5))
        nav_panel.setBorder(BorderFactory.createEmptyBorder(0, 5, 5, 5))
        nav_panel.setMinimumSize(Dimension(100, 0))

        # Header sits on the same row as the Search bar
        nav_header = JPanel(BorderLayout())
        nav_header.setBorder(BorderFactory.createEmptyBorder(5, 0, 5, 0))
        nav_header.setPreferredSize(Dimension(0, search_panel.getPreferredSize().height))
        lbl_nav = JLabel("Titles")
        nav_header.add(lbl_nav, BorderLayout.CENTER)
        nav_panel.add(nav_header, BorderLayout.NORTH)

        self.nav_list_model = DefaultListModel()
        self.nav_list = JList(self.nav_list_model)
        self.nav_list.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        self.nav_list.addListSelectionListener(NavSelectListener(self))
        self.nav_list.addMouseListener(NavClickListener(self))

        nav_scroll = JScrollPane(self.nav_list)
        nav_panel.add(nav_scroll, BorderLayout.CENTER)

        left_panel = JPanel(BorderLayout())
        left_panel.setMinimumSize(Dimension(300, 0))
        left_panel.add(search_panel, BorderLayout.NORTH)
        left_panel.add(scroll_pane, BorderLayout.CENTER)

        # Draggable divider so the user can resize the titles list
        self.split_pane = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, left_panel, nav_panel)
        self.split_pane.setResizeWeight(1.0)
        self.split_pane.setContinuousLayout(True)
        self.split_pane.setBorder(None)
        self.split_pane.addComponentListener(InitialDividerListener(self.split_pane, 200))

        self.panel.add(self.split_pane, BorderLayout.CENTER)
        self.panel.add(control_panel, BorderLayout.SOUTH)

    # Context Menu MenuItems generator
    def createMenuItems(self, invocation):
        menu_list = ArrayList()
        selection_bounds = invocation.getSelectionBounds()
        ctx = invocation.getInvocationContext()
        
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
                    
        # Add Creds (Insert) feature in editors
        if ctx in [invocation.CONTEXT_MESSAGE_EDITOR_REQUEST, invocation.CONTEXT_MESSAGE_EDITOR_RESPONSE]:
            if self.blocks:
                if menu_list.size() > 0:
                    sep = JMenuItem("------------------------------")
                    sep.setEnabled(False)
                    menu_list.add(sep)
                    
                insert_menu = JMenu("Add Creds")
                added_any = False
                for block in self.blocks:
                    val = block.txt_value.getText().strip()
                    if val:
                        title = block.txt_title.getText().strip()
                        if not title:
                            title = "Untitled"
                        item = JMenuItem(title, actionPerformed=lambda x, v=val: self.insert_cred_to_editor(invocation, v))
                        insert_menu.add(item)
                        added_any = True
                
                if added_any:
                    menu_list.add(insert_menu)
            
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

    def insert_cred_to_editor(self, invocation, value):
        messages = invocation.getSelectedMessages()
        if not messages:
            return
            
        bounds = invocation.getSelectionBounds()
        ctx = invocation.getInvocationContext()
        is_request = (ctx == invocation.CONTEXT_MESSAGE_EDITOR_REQUEST)
        
        if is_request:
            data = messages[0].getRequest()
        else:
            data = messages[0].getResponse()
            
        if data is None:
            return
            
        try:
            data_str = self._helpers.bytesToString(data)
            
            if bounds is not None:
                start = bounds[0]
                end = bounds[1]
                new_data_str = data_str[:start] + value + data_str[end:]
            else:
                new_data_str = data_str + value
                
            new_bytes = self._helpers.stringToBytes(new_data_str)
            
            if is_request:
                messages[0].setRequest(new_bytes)
            else:
                messages[0].setResponse(new_bytes)
                
            ToastManager.show("Inserted cred successfully!", None, 1500)
        except Exception as e:
            print("[-] Error inserting cred to editor: " + str(e))

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
        self.update_nav_list()
        self.schedule_save()

    def new_title(self, event):
        # Clear the search filter so the new block isn't hidden
        if self.txt_search.getText():
            self.txt_search.setText("")

        self.add_block("")
        block = self.blocks[-1]

        class FocusNewBlockRunnable(Runnable):
            def __init__(self, extender, b):
                self.extender = extender
                self.b = b
            def run(self):
                self.extender.select_block(self.b)
                self.b.txt_title.requestFocusInWindow()
                self.b.txt_title.selectAll()

        # Run after the layout pass so scrolling to the new block has real bounds
        SwingUtilities.invokeLater(FocusNewBlockRunnable(self, block))

    def remove_block(self, block):
        if block in self.blocks:
            if self.active_block is block:
                self.active_block = None
            self.blocks.remove(block)
            self.blocks_container.remove(block.panel)
            self.blocks_container.revalidate()
            self.blocks_container.repaint()
            self.update_count()
            self.update_nav_list()
            self.schedule_save()

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
                self.extender.update_nav_list()
                self.extender.schedule_save()

        SwingUtilities.invokeLater(SwingRunnable(self))

    def update_count(self):
        self.lbl_count.setText("Total: " + str(len(self.blocks)))
        self.update_select_all()

    def update_select_all(self):
        # "Select All" is ticked only when every block is ticked
        all_selected = len(self.blocks) > 0 and all(b.checkbox.isSelected() for b in self.blocks)
        self.chk_tick_all.setSelected(all_selected)

    def request_nav_update(self):
        if self._nav_refresh_pending:
            return
        self._nav_refresh_pending = True
        class NavRefreshRunnable(Runnable):
            def __init__(self, extender):
                self.extender = extender
            def run(self):
                self.extender._nav_refresh_pending = False
                self.extender.update_nav_list()
        SwingUtilities.invokeLater(NavRefreshRunnable(self))

    def update_nav_list(self):
        self._nav_updating = True
        try:
            self.nav_list_model.clear()
            for block in self.blocks:
                title = block.txt_title.getText().strip()
                if not title:
                    title = "Untitled"
                self.nav_list_model.addElement(title)
            if self.active_block in self.blocks:
                self.nav_list.setSelectedIndex(self.blocks.index(self.active_block))
        finally:
            self._nav_updating = False

    def select_block(self, block, scroll=True):
        class SelectRunnable(Runnable):
            def __init__(self, extender, b, do_scroll):
                self.extender = extender
                self.b = b
                self.do_scroll = do_scroll
            def run(self):
                ext = self.extender
                try:
                    if ext.active_block is not None and ext.active_block is not self.b:
                        ext.active_block.set_highlight(False)
                    ext.active_block = self.b
                    self.b.set_highlight(True)

                    if self.b in ext.blocks:
                        ext._nav_updating = True
                        try:
                            idx = ext.blocks.index(self.b)
                            ext.nav_list.setSelectedIndex(idx)
                            ext.nav_list.ensureIndexIsVisible(idx)
                        finally:
                            ext._nav_updating = False

                    if self.do_scroll:
                        self.b.panel.scrollRectToVisible(Rectangle(0, 0, self.b.panel.getWidth(), self.b.panel.getHeight()))
                except Exception as e:
                    print("[-] Error selecting block: " + str(e))
        SwingUtilities.invokeLater(SelectRunnable(self, block, scroll))

    def clear_data(self, event):
        self.active_block = None
        self.blocks = []
        self.blocks_container.removeAll()
        self.blocks_container.revalidate()
        self.blocks_container.repaint()
        self.update_count()
        self.update_nav_list()
        self.schedule_save()

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

    def get_selected_items(self):
        items = []
        for block in self.blocks:
            if block.checkbox.isSelected():
                val = block.txt_value.getText().strip()
                title = block.txt_title.getText().strip()
                if val:
                    items.append({"title": title, "value": val})
        return items

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
        items = self.get_selected_items()
        if not items:
            return
        
        parent_window = SwingUtilities.getWindowAncestor(self.panel)
        if parent_window is None:
            parent_window = Frame()
            
        panel = JPanel()
        panel.setLayout(BoxLayout(panel, BoxLayout.Y_AXIS))
        panel.add(JLabel("Choose export format:"))
        panel.add(Box.createVerticalStrut(10))
        chk_include_title = JCheckBox("Include titles (e.g. Title: CookieValue)")
        
        pref = self._callbacks.loadExtensionSetting("SaveCreds_ExportIncludeTitle")
        if pref == "True":
            chk_include_title.setSelected(True)
        else:
            chk_include_title.setSelected(False)
            
        panel.add(chk_include_title)
        
        result = JOptionPane.showConfirmDialog(parent_window, panel, "Export Options", JOptionPane.OK_CANCEL_OPTION, JOptionPane.PLAIN_MESSAGE)
        if result != JOptionPane.OK_OPTION:
            return
            
        include_title = chk_include_title.isSelected()
        self._callbacks.saveExtensionSetting("SaveCreds_ExportIncludeTitle", str(include_title))
            
        file_path = self.choose_file(parent_window, "Save Wordlist", True, "wordlist.txt")

        if file_path:
            if not file_path.endswith(".txt"):
                file_path += ".txt"

            # Write file in background thread to avoid UI lag/freeze
            def do_write():
                try:
                    with codecs.open(file_path, "w", "utf-8") as f:
                        for i, item in enumerate(items):
                            if include_title:
                                f.write(item["title"] + u": \n" + item["value"] + u"\n")
                                if i < len(items) - 1:
                                    f.write(u"\n")
                            else:
                                f.write(item["value"] + u"\n")
                    print("[+] Wordlist exported successfully to: " + file_path)
                    ToastManager.show("Exported successfully!", self.panel, 1500)
                except Exception as e:
                    print("[-] Error saving file: " + str(e))
            
            threading.Thread(target=do_write).start()

    def choose_file(self, parent, title, save, default_name=None):
        # Swing chooser (not the native FileDialog) so it follows Burp's light/dark theme
        chooser = JFileChooser()
        chooser.setDialogTitle(title)

        last_dir = self._callbacks.loadExtensionSetting("SaveCreds_LastDir")
        if last_dir and File(last_dir).isDirectory():
            chooser.setCurrentDirectory(File(last_dir))
        if save and default_name:
            chooser.setSelectedFile(File(chooser.getCurrentDirectory(), default_name))

        if save:
            result = chooser.showSaveDialog(parent)
        else:
            result = chooser.showOpenDialog(parent)
        if result != JFileChooser.APPROVE_OPTION:
            return None

        selected = chooser.getSelectedFile()
        if save and not selected.getName().endswith(".txt"):
            selected = File(selected.getParentFile(), selected.getName() + ".txt")
        if save and selected.exists():
            answer = JOptionPane.showConfirmDialog(parent, selected.getName() + " already exists. Overwrite?", "Confirm", JOptionPane.YES_NO_OPTION)
            if answer != JOptionPane.YES_OPTION:
                return None

        if selected.getParentFile() is not None:
            self._callbacks.saveExtensionSetting("SaveCreds_LastDir", selected.getParentFile().getAbsolutePath())
        return selected.getAbsolutePath()

    def parse_import_entries(self, lines, with_cookie):
        # Returns [(title, value)]. With cookies: entries are blank-line separated,
        # first line is the title, remaining lines are the cookie value.
        entries = []
        if not with_cookie:
            for line in lines:
                title = line.strip()
                if title:
                    entries.append((title, ""))
            return entries

        group = []
        for raw in lines + [u""]:
            line = raw.rstrip("\r\n")
            if line.strip() == "":
                if group:
                    # Exported files write "Title: " so drop that trailing colon
                    title = group[0].strip().rstrip(":").strip()
                    value = "\n".join([l.strip() for l in group[1:]])
                    entries.append((title, value))
                    group = []
            else:
                group.append(line)
        return entries

    def import_data(self, event):
        parent_window = SwingUtilities.getWindowAncestor(self.panel)
        if parent_window is None:
            parent_window = Frame()

        options = ["Titles only", "Titles + Cookies", "Cancel"]
        choice = JOptionPane.showOptionDialog(
            parent_window,
            "Titles only: one title per line.\n"
            "Titles + Cookies: each entry is a title line followed by its cookie line(s),\n"
            "entries separated by a blank line.",
            "Import",
            JOptionPane.DEFAULT_OPTION, JOptionPane.QUESTION_MESSAGE, None, options, options[0])
        if choice not in (0, 1):
            return
        with_cookie = (choice == 1)

        file_path = self.choose_file(parent_window, "Import Titles + Cookies" if with_cookie else "Import Titles", False)

        if file_path:
            def do_import():
                try:
                    with codecs.open(file_path, "r", "utf-8-sig") as f:
                        lines = f.readlines()

                    entries = self.parse_import_entries(lines, with_cookie)
                    for title, value in entries:
                        class SwingRunnable(Runnable):
                            def __init__(self, ext, t, v):
                                self.ext = ext
                                self.t = t
                                self.v = v
                            def run(self):
                                self.ext.add_block(self.v, title=self.t)
                        SwingUtilities.invokeLater(SwingRunnable(self, title, value))
                    print("[+] Imported " + str(len(entries)) + " entries from: " + file_path)
                except Exception as e:
                    print("[-] Error importing: " + str(e))

            threading.Thread(target=do_import).start()

    # Required ITab interfaces
    def getTabCaption(self):
        return "Save Creds"
        
    def getUiComponent(self):
        return self.panel