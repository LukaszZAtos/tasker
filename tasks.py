import curses
import uuid
from datetime import datetime
import sqlite3

class Task:
    def __init__(self, task_id, name, due_date, ticket_ref, description, status="Pending"):
        self.id = task_id
        self.name = name
        self.due_date = due_date if due_date else (datetime.now().replace(hour=23, minute=59, second=59).strftime('%Y-%m-%d %H:%M:%S'))
        self.ticket_ref = ticket_ref
        self.description = description  # Markdown-supported
        self.status = status
        self.comments = []
        self.dependencies = []

    def add_comment(self, comment):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.comments.append(f"[{timestamp}] {comment}")

    def add_dependency(self, task):
        if task.id not in self.dependencies:
            self.dependencies.append(task.id)

class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.selected_index = 0
        self.db_file = "tasks.db"
        self.show_comments = False  # Nowe pole do przełączania widoczności komentarzy
        self.search_mode = False    # Nowe pole do trybu wyszukiwania
        self.search_results = []    # Lista wyników wyszukiwania
        self.init_db()
        self.load_tasks_from_db()

    def init_db(self):
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
                                id TEXT PRIMARY KEY,
                                name TEXT,
                                due_date TEXT,
                                ticket_ref TEXT,
                                description TEXT,
                                status TEXT
                              )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS comments (
                                task_id TEXT,
                                comment TEXT,
                                timestamp TEXT
                              )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS dependencies (
                                task_id TEXT,
                                dependency_id TEXT,
                                FOREIGN KEY(task_id) REFERENCES tasks(id),
                                FOREIGN KEY(dependency_id) REFERENCES tasks(id)
                              )''')

    def load_tasks_from_db(self):
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks')
            rows = cursor.fetchall()
            for row in rows:
                task = Task(row[0], row[1], row[2], row[3], row[4], row[5])
                self.tasks[task.id] = task

            cursor.execute('SELECT task_id, comment, timestamp FROM comments')
            rows = cursor.fetchall()
            for task_id, comment, timestamp in rows:
                if task_id in self.tasks:
                    self.tasks[task_id].comments.append(f"[{timestamp}] {comment}")

            # Ładowanie zależności
            cursor.execute('SELECT task_id, dependency_id FROM dependencies')
            rows = cursor.fetchall()
            for task_id, dependency_id in rows:
                if task_id in self.tasks and dependency_id in self.tasks:
                    self.tasks[task_id].dependencies.append(dependency_id)

    def save_task_to_db(self, task):
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            # Zapisz podstawowe informacje o zadaniu
            cursor.execute('''REPLACE INTO tasks (id, name, due_date, ticket_ref, description, status)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (task.id, task.name, task.due_date, task.ticket_ref, task.description, task.status))
            
            # Zaktualizuj zależności
            cursor.execute('DELETE FROM dependencies WHERE task_id = ?', (task.id,))
            for dependency_id in task.dependencies:
                cursor.execute('INSERT INTO dependencies (task_id, dependency_id) VALUES (?, ?)',
                             (task.id, dependency_id))

    def save_comment_to_db(self, task_id, comment):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO comments (task_id, comment, timestamp) VALUES (?, ?, ?)', 
                         (task_id, comment, timestamp))

    def add_task(self, name, due_date, ticket_ref, description, status="Pending"):
        task = Task(str(uuid.uuid4()), name, due_date, ticket_ref, description, status)
        self.tasks[task.id] = task
        self.save_task_to_db(task)

    def edit_task(self, task_id, name=None, due_date=None, ticket_ref=None, description=None, status=None):
        task = self.tasks.get(task_id)
        if not task:
            return
        if name:
            task.name = name
        if due_date:
            task.due_date = due_date
        if ticket_ref:
            task.ticket_ref = ticket_ref
        if description:
            task.description = description
        if status:
            task.status = status
        self.save_task_to_db(task)

    def get_task_by_index(self, index):
        if 0 <= index < len(self.tasks):
            return list(self.tasks.values())[index]
        return None

    def init_colors(self):
        curses.start_color()
        # Podstawowe kolory
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)     # Wybrane wiersze
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLUE)     # Nagłówki
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # Tytuły sekcji
        curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)    # Status: Pending
        curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)      # Status: Completed
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_RED)      # Przeterminowane
        curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_YELLOW)   # Pilne
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_GREEN)    # W terminie
        curses.init_pair(9, curses.COLOR_WHITE, curses.COLOR_BLACK)    # Podstawowy tekst
        curses.init_pair(10, curses.COLOR_BLACK, curses.COLOR_WHITE)   # Przyciski

    def check_due_date(self, task):
        if not task.due_date:
            return "normal"
        
        try:
            due_date = datetime.strptime(task.due_date.split()[0], '%Y-%m-%d')
            now = datetime.now()
            
            if due_date.date() < now.date():
                return "overdue"
            
            time_left = due_date - now
            if time_left.days < 1:
                return "urgent"
            elif time_left.days >= 1:
                return "plenty_of_time"
                
            return "normal"
        except ValueError:
            return "normal"

    def handle_input(self, stdscr):
        self.init_colors()
        curses.curs_set(0)

        while True:
            self.render_table(stdscr)
            key = stdscr.getch()

            if key == curses.KEY_UP:
                self.selected_index = max(0, self.selected_index - 1)
            elif key == curses.KEY_DOWN:
                self.selected_index = min(len(self.tasks) - 1, self.selected_index + 1)
            elif key == ord("q"):
                break
            elif key == ord("a"):
                self.add_task_ui(stdscr)
            elif key == ord("s"):
                self.change_status_ui(stdscr)
            elif key == curses.KEY_ENTER or key == 10:
                task = self.get_task_by_index(self.selected_index)
                if task:
                    self.render_task_details(stdscr, task)
            elif key == ord("c"):
                self.add_comment_ui(stdscr)
            elif key == ord("d"):
                self.add_dependency_ui(stdscr)
            elif key == ord("m"):
                self.show_comments = not self.show_comments
            elif key == ord("/"):
                self.search_ui(stdscr)
            elif key == ord("x"):
                self.delete_task_ui(stdscr)

    def render_table(self, stdscr):
        height, width = stdscr.getmaxyx()
        stdscr.clear()

        # Upewnij się, że mamy wystarczająco miejsca
        if height < 10 or width < 40:
            try:
                stdscr.addstr(0, 0, "Terminal too small!")
                stdscr.refresh()
            except curses.error:
                pass
            return

        # Oblicz szerokości kolumn na podstawie dostępnej przestrzeni
        available_width = width - 6  # Odejmij marginesy i znaki ramki
        
        # Proporcje szerokości kolumn (suma = 100)
        column_ratios = {
            "#": 5,          # 5% szerokości
            "Name": 25,      # 25% szerokości
            "Due Date": 15,  # 15% szerokości
            "Ticket Ref": 15,# 15% szerokości
            "Status": 10,    # 10% szerokości
            "Dependencies": 30# 30% szerokości
        }
        
        # Oblicz rzeczywiste szerokości kolumn
        column_widths = {}
        for column, ratio in column_ratios.items():
            column_widths[column] = max(10, int((available_width * ratio) / 100))
        
        # Dostosuj ostatnią kolumnę, aby wykorzystać pozostałą przestrzeń
        total_used = sum(column_widths.values())
        if total_used < available_width:
            column_widths["Dependencies"] += (available_width - total_used)

        # Rysuj ramkę główną z marginesem
        self.draw_box(stdscr, 0, 0, height-2, width-1)
        
        # Tytuł aplikacji w ozdobnej ramce
        title = "│ Task Manager │"
        title_x = max(0, min((width - len(title)) // 2, width-len(title)))
        stdscr.addstr(0, title_x, "┌" + "─" * (len(title)-2) + "┐", curses.color_pair(2))
        stdscr.addstr(1, title_x, title, curses.color_pair(2) | curses.A_BOLD)
        stdscr.addstr(2, title_x, "└" + "─" * (len(title)-2) + "┘", curses.color_pair(2))

        # Menu i skróty klawiszowe w ramce
        shortcuts = [
            "↑/↓ Navigate", "ENTER View", "A Add", "S Status",
            "C Comment", "D Dependency", "M Comments", "X Delete",
            "/ Search", "Q Quit"
        ]
        shortcut_str = " | ".join(shortcuts)
        menu_x = (width - len(shortcut_str)) // 2
        stdscr.addstr(4, 2, "╔" + "═" * (width-4) + "╗", curses.color_pair(9))
        stdscr.addstr(5, menu_x, shortcut_str, curses.color_pair(9) | curses.A_DIM)
        stdscr.addstr(6, 2, "╚" + "═" * (width-4) + "╝", curses.color_pair(9))

        # Nagłówki tabeli
        headers = ["#", "Name", "Due Date", "Ticket Ref", "Status", "Dependencies"]
        header_format = "│".join(f"{h:<{column_widths[h]}}" for h in headers)
        stdscr.addstr(8, 2, "┌" + "─" * (width-4) + "┐", curses.color_pair(2))
        stdscr.addstr(9, 2, header_format, curses.color_pair(2) | curses.A_BOLD)
        stdscr.addstr(10, 2, "├" + "─" * (width-4) + "┤", curses.color_pair(2))

        # Zawartość tabeli
        row_offset = 11
        for idx, task in enumerate(self.tasks.values()):
            prefix = "→" if idx == self.selected_index else " "
            due_status = self.check_due_date(task)
            
            if due_status == "overdue":
                base_color = curses.color_pair(6)
            elif due_status == "urgent":
                base_color = curses.color_pair(7)
            elif due_status == "plenty_of_time":
                base_color = curses.color_pair(8)
            else:
                base_color = curses.color_pair(9)

            dependencies = ", ".join([self.tasks[dep].name for dep in task.dependencies if dep in self.tasks])
            
            # Formatuj każdą kolumnę osobno z odpowiednią szerokością
            row_data = [
                f"{prefix}{idx}".ljust(column_widths["#"]),
                task.name[:column_widths["Name"]].ljust(column_widths["Name"]),
                task.due_date[:column_widths["Due Date"]].ljust(column_widths["Due Date"]),
                task.ticket_ref[:column_widths["Ticket Ref"]].ljust(column_widths["Ticket Ref"]),
                task.status[:column_widths["Status"]].ljust(column_widths["Status"]),
                dependencies[:column_widths["Dependencies"]].ljust(column_widths["Dependencies"])
            ]
            row = "│".join(row_data)
            
            current_row = row_offset + idx
            stdscr.addstr(current_row, 2, row, base_color | curses.A_BOLD if idx == self.selected_index else base_color)

            # Komentarze
            if self.show_comments and idx == self.selected_index:
                if task.comments:
                    stdscr.addstr(current_row + 1, 4, "╭─ Recent Comments:", curses.color_pair(2))
                    for cidx, comment in enumerate(task.comments[-3:]):
                        stdscr.addstr(current_row + 2 + cidx, 4, f"╰→ {comment}", curses.color_pair(2))
                    row_offset += len(task.comments[-3:]) + 1

        # Dolna ramka tabeli
        stdscr.addstr(row_offset + len(self.tasks), 2, "└" + "─" * (width-4) + "┘", curses.color_pair(2))
        stdscr.refresh()

    def draw_box(self, stdscr, y1, x1, y2, x2):
        """Pomocnicza metoda do rysowania ramek"""
        height, width = stdscr.getmaxyx()
        
        # Upewnij się, że nie wychodzimy poza granice ekranu
        y2 = min(y2, height-1)
        x2 = min(x2, width-1)
        
        try:
            # Górna krawędź
            if y1 >= 0 and y1 < height:
                stdscr.addstr(y1, x1, "╔" + "═" * (x2-x1-1) + "╗")
            
            # Boczne krawędzie
            for y in range(y1+1, y2):
                if y < height:
                    if x1 >= 0 and x1 < width:
                        stdscr.addstr(y, x1, "║")
                    if x2 >= 0 and x2 < width:
                        stdscr.addstr(y, x2, "║")
            
            # Dolna krawędź
            if y2 >= 0 and y2 < height:
                stdscr.addstr(y2, x1, "╚" + "═" * (x2-x1-1) + "╝")
        except curses.error:
            pass  # Ignoruj błędy pisania poza ekranem

    def render_task_details(self, stdscr, task):
        height, width = stdscr.getmaxyx()
        stdscr.clear()
        
        # Główna ramka
        self.draw_box(stdscr, 0, 0, height-1, width-1)
        
        # Tytuł
        title = f"│ Task Details: {task.name} │"
        title_x = (width - len(title)) // 2
        stdscr.addstr(1, title_x, title, curses.color_pair(3) | curses.A_BOLD)
        
        # Pola w ozdobnej ramce
        fields = [
            ("Name", task.name),
            ("Due Date", task.due_date),
            ("Ticket Ref", task.ticket_ref),
            ("Description", task.description),
            ("Status", task.status),
            ("Dependencies", ", ".join([self.tasks[dep].name for dep in task.dependencies if dep in self.tasks])),
        ]

        # Ramka dla pól
        stdscr.addstr(3, 2, "╔" + "═" * (width-6) + "╗", curses.color_pair(2))
        
        for idx, (field_name, field_value) in enumerate(fields):
            prefix = "→" if idx == current_field else " "
            if idx == current_field:
                stdscr.addstr(idx + 4, 4, f"{prefix} {field_name}: ", curses.color_pair(1) | curses.A_BOLD)
            else:
                stdscr.addstr(idx + 4, 4, f"{prefix} {field_name}: ", curses.color_pair(9))
            
            if field_name == "Status":
                color = (curses.color_pair(4) if field_value == "Pending"
                        else curses.color_pair(3) if field_value == "In Progress"
                        else curses.color_pair(5))
                stdscr.addstr(field_value, color | curses.A_BOLD)
            else:
                stdscr.addstr(str(field_value))

        stdscr.addstr(len(fields) + 4, 2, "╚" + "═" * (width-6) + "╝", curses.color_pair(2))

        # Komentarze w osobnej ramce
        comment_start = len(fields) + 6
        stdscr.addstr(comment_start, 2, "╔══ Comments ═" + "═" * (width-15) + "╗", curses.color_pair(3))
        for idx, comment in enumerate(task.comments):
            stdscr.addstr(comment_start + 1 + idx, 4, f"• {comment}", curses.color_pair(9))
        stdscr.addstr(comment_start + len(task.comments) + 1, 2, "╚" + "═" * (width-4) + "╝", curses.color_pair(3))

        # Instrukcje w dolnej części ekranu
        instructions = [
            "↑/↓ Navigate", "ENTER Edit", "D Remove Dependency",
            "C Add Comment", "ESC Return"
        ]
        instr_str = " │ ".join(instructions)
        instr_x = (width - len(instr_str)) // 2
        stdscr.addstr(height-2, instr_x, instr_str, curses.color_pair(10) | curses.A_DIM)

        stdscr.refresh()

    def edit_field_ui(self, stdscr, task, field_name):
        curses.echo()
        stdscr.clear()
        stdscr.addstr(0, 0, f"Edit {field_name}", curses.color_pair(3) | curses.A_BOLD)

        current_value = getattr(task, field_name.lower().replace(" ", "_"))
        stdscr.addstr(1, 0, f"Current value: {current_value}")
        stdscr.addstr(2, 0, "New value: ")
        
        if field_name == "Status":
            self.change_status_ui(stdscr)
            return

        new_value = stdscr.getstr(2, 11, 100).decode("utf-8")
        if new_value:
            if field_name == "Name":
                self.edit_task(task.id, name=new_value)
            elif field_name == "Due Date":
                self.edit_task(task.id, due_date=new_value)
            elif field_name == "Ticket Ref":
                self.edit_task(task.id, ticket_ref=new_value)
            elif field_name == "Description":
                self.edit_task(task.id, description=new_value)

        curses.noecho()
        stdscr.addstr(4, 0, f"{field_name} updated successfully!", curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(5, 0, "Press any key to return...", curses.A_DIM)
        stdscr.refresh()
        stdscr.getch()

    def remove_dependency_ui(self, stdscr, task):
        if not task.dependencies:
            stdscr.addstr(2, 0, "No dependencies to remove. Press any key to return...", curses.A_DIM)
            stdscr.refresh()
            stdscr.getch()
            return

        current_dep_index = 0
        dependencies = [self.tasks[dep] for dep in task.dependencies if dep in self.tasks]
        
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, "Remove Dependency", curses.color_pair(3) | curses.A_BOLD)
            stdscr.addstr(1, 0, f"From Task: {task.name}", curses.color_pair(2))
            stdscr.addstr(2, 0, "Select dependency to remove:")

            for idx, dep_task in enumerate(dependencies):
                status_color = (curses.color_pair(4) if dep_task.status == "Pending" 
                              else curses.color_pair(3) if dep_task.status == "In Progress"
                              else curses.color_pair(5))
                
                if idx == current_dep_index:
                    stdscr.addstr(3 + idx, 0, f"> {dep_task.name} [{dep_task.status}]", 
                                curses.color_pair(1) | curses.A_BOLD)
                else:
                    stdscr.addstr(3 + idx, 2, f"{dep_task.name} [{dep_task.status}]", 
                                status_color)

            stdscr.addstr(len(dependencies) + 4, 0, 
                         "Use UP/DOWN arrows to select, ENTER to remove, ESC to cancel", 
                         curses.A_DIM)
            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_UP:
                current_dep_index = max(0, current_dep_index - 1)
            elif key == curses.KEY_DOWN:
                current_dep_index = min(len(dependencies) - 1, current_dep_index + 1)
            elif key == 10 or key == curses.KEY_ENTER:  # Enter
                dep_to_remove = dependencies[current_dep_index]
                task.dependencies.remove(dep_to_remove.id)
                self.save_task_to_db(task)
                
                stdscr.addstr(len(dependencies) + 6, 0, 
                             "Dependency removed successfully!", 
                             curses.color_pair(4) | curses.A_BOLD)
                stdscr.addstr(len(dependencies) + 7, 0, 
                             "Press any key to return...", 
                             curses.A_DIM)
                stdscr.refresh()
                stdscr.getch()
                break
            elif key == 27:  # ESC
                break

    def add_task_ui(self, stdscr):
        curses.echo()
        stdscr.clear()
        stdscr.addstr(0, 0, "Add New Task", curses.color_pair(3) | curses.A_BOLD)

        stdscr.addstr(1, 0, "Name: ")
        name = stdscr.getstr(1, 6, 50).decode("utf-8")

        stdscr.addstr(2, 0, "Due Date (YYYY-MM-DD) [Leave empty for default end of today]: ")
        due_date = stdscr.getstr(2, 50, 10).decode("utf-8")
        due_date = due_date if due_date else None

        stdscr.addstr(3, 0, "Ticket Reference: ")
        ticket_ref = stdscr.getstr(3, 18, 50).decode("utf-8")
        
        stdscr.addstr(4, 0, "Description: ")
        description = stdscr.getstr(4, 12, 100).decode("utf-8")

        stdscr.addstr(5, 0, "Status [Pending/Completed]: ")
        status = stdscr.getstr(5, 25, 10).decode("utf-8")
        status = status if status else "Pending"

        self.add_task(name, due_date, ticket_ref, description, status)
        curses.noecho()
        stdscr.addstr(7, 0, "Task added successfully!", curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(8, 0, "Press any key to return...", curses.A_DIM)
        stdscr.getch()

    def add_comment_ui(self, stdscr):
        curses.echo()
        stdscr.clear()
        stdscr.addstr(0, 0, "Add Comment", curses.color_pair(3) | curses.A_BOLD)

        task = self.get_task_by_index(self.selected_index)
        if not task:
            stdscr.addstr(3, 0, "No task selected. Press any key to return...", curses.A_DIM)
            stdscr.refresh()
            stdscr.getch()
            return

        stdscr.addstr(1, 0, "Comment: ")
        comment = stdscr.getstr(1, 9, 100).decode("utf-8")

        task.add_comment(comment)
        self.save_comment_to_db(task.id, comment)

        curses.noecho()
        stdscr.addstr(3, 0, "Comment added successfully!", curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(4, 0, "Press any key to return...", curses.A_DIM)
        stdscr.getch()

    def change_status_ui(self, stdscr):
        stdscr.clear()
        stdscr.addstr(0, 0, "Change Task Status", curses.color_pair(3) | curses.A_BOLD)

        task = self.get_task_by_index(self.selected_index)
        if not task:
            stdscr.addstr(2, 0, "No task selected. Press any key to return...", curses.A_DIM)
            stdscr.refresh()
            stdscr.getch()
            return

        statuses = ["Pending", "In Progress", "Completed"]
        current_status_index = statuses.index(task.status) if task.status in statuses else 0
        
        while True:
            stdscr.addstr(1, 0, f"Current Status: ")
            for i, status in enumerate(statuses):
                if i == current_status_index:
                    # Wybierz odpowiedni kolor dla statusu
                    if status == "Pending":
                        color = curses.color_pair(4)  # Zielony
                    elif status == "In Progress":
                        color = curses.color_pair(3)  # Żółty
                    else:  # Completed
                        color = curses.color_pair(5)  # Czerwony
                    stdscr.addstr(status, color | curses.A_BOLD)  # Podświetlony status
                else:
                    stdscr.addstr(" " + status)
                if i < len(statuses) - 1:
                    stdscr.addstr(" | ")

            stdscr.addstr(3, 0, "Use LEFT/RIGHT arrows to change status, ENTER to confirm, ESC to cancel", curses.A_DIM)
            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_LEFT:
                current_status_index = max(0, current_status_index - 1)
            elif key == curses.KEY_RIGHT:
                current_status_index = min(len(statuses) - 1, current_status_index + 1)
            elif key == 10 or key == curses.KEY_ENTER:  # Enter
                new_status = statuses[current_status_index]
                self.edit_task(task.id, status=new_status)
                stdscr.addstr(5, 0, "Status updated successfully!", curses.color_pair(4) | curses.A_BOLD)
                stdscr.addstr(6, 0, "Press any key to return...", curses.A_DIM)
                stdscr.refresh()
                stdscr.getch()
                break
            elif key == 27:  # ESC
                break

    def add_dependency_ui(self, stdscr):
        stdscr.clear()
        stdscr.addstr(0, 0, "Add Dependency", curses.color_pair(3) | curses.A_BOLD)

        task = self.get_task_by_index(self.selected_index)
        if not task:
            stdscr.addstr(2, 0, "No task selected. Press any key to return...", curses.A_DIM)
            stdscr.refresh()
            stdscr.getch()
            return

        available_tasks = [t for t in self.tasks.values() if t.id != task.id]  # wykluczamy aktualny task
        if not available_tasks:
            stdscr.addstr(2, 0, "No other tasks available to add as dependency. Press any key to return...", curses.A_DIM)
            stdscr.refresh()
            stdscr.getch()
            return

        current_dep_index = 0
        
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, "Add Dependency", curses.color_pair(3) | curses.A_BOLD)
            stdscr.addstr(1, 0, f"Selected Task: {task.name}", curses.color_pair(2))
            stdscr.addstr(2, 0, "Available Tasks:")

            # Wyświetl listę dostępnych zadań
            for idx, dep_task in enumerate(available_tasks):
                status_color = (curses.color_pair(4) if dep_task.status == "Pending" 
                              else curses.color_pair(3) if dep_task.status == "In Progress"
                              else curses.color_pair(5))
                
                if idx == current_dep_index:
                    stdscr.addstr(3 + idx, 0, f"> {dep_task.name} [{dep_task.status}]", 
                                curses.color_pair(1) | curses.A_BOLD)
                else:
                    stdscr.addstr(3 + idx, 2, f"{dep_task.name} [{dep_task.status}]", 
                                status_color)

            stdscr.addstr(len(available_tasks) + 4, 0, 
                         "Use UP/DOWN arrows to select, ENTER to confirm, ESC to cancel", 
                         curses.A_DIM)
            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_UP:
                current_dep_index = max(0, current_dep_index - 1)
            elif key == curses.KEY_DOWN:
                current_dep_index = min(len(available_tasks) - 1, current_dep_index + 1)
            elif key == 10 or key == curses.KEY_ENTER:  # Enter
                dependency_task = available_tasks[current_dep_index]
                task.add_dependency(dependency_task)
                self.save_task_to_db(task)
                
                stdscr.addstr(len(available_tasks) + 6, 0, 
                             "Dependency added successfully!", 
                             curses.color_pair(4) | curses.A_BOLD)
                stdscr.addstr(len(available_tasks) + 7, 0, 
                             "Press any key to return...", 
                             curses.A_DIM)
                stdscr.refresh()
                stdscr.getch()
                break
            elif key == 27:  # ESC
                break

    def search_ui(self, stdscr):
        curses.echo()
        stdscr.clear()
        stdscr.addstr(0, 0, "Search Tasks", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr(1, 0, "Enter search term (task name, ticket ref): ")
        search_term = stdscr.getstr(1, 40, 50).decode("utf-8").lower()

        if search_term:
            matching_tasks = []
            for task in self.tasks.values():
                if (search_term.lower() in task.name.lower() or 
                    search_term.lower() in task.ticket_ref.lower() or 
                    search_term.lower() in task.description.lower()):
                    matching_tasks.append(task)

            if matching_tasks:
                current_index = 0
                while True:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Search Results for: {search_term}", 
                                curses.color_pair(3) | curses.A_BOLD)
                    
                    # Wyświetl instrukcje
                    stdscr.addstr(1, 0, "Use UP/DOWN to navigate, ENTER to view details, V to select, ESC to cancel",
                                curses.A_DIM)

                    for idx, task in enumerate(matching_tasks):
                        status_color = (curses.color_pair(4) if task.status == "Pending"
                                      else curses.color_pair(3) if task.status == "In Progress"
                                      else curses.color_pair(5))
                        
                        if idx == current_index:
                            stdscr.addstr(idx + 3, 0, f"> {task.name} [{task.status}] - {task.ticket_ref}", 
                                        curses.color_pair(1) | curses.A_BOLD)
                            
                            # Wyświetl dodatkowe informacje o zaznaczonym tasku
                            stdscr.addstr(idx + 4, 2, f"Description: {task.description[:50]}...", 
                                        curses.color_pair(2))
                        else:
                            stdscr.addstr(idx + 3, 2, f"{task.name} [{task.status}] - {task.ticket_ref}", 
                                        status_color)

                    stdscr.refresh()

                    key = stdscr.getch()
                    if key == curses.KEY_UP:
                        current_index = max(0, current_index - 1)
                    elif key == curses.KEY_DOWN:
                        current_index = min(len(matching_tasks) - 1, current_index)
                    elif key == 10 or key == curses.KEY_ENTER:  # Enter - pokaż szczegóły
                        selected_task = matching_tasks[current_index]
                        self.selected_index = list(self.tasks.values()).index(selected_task)
                        self.render_task_details(stdscr, selected_task)
                        break
                    elif key == ord('v'):  # V - wybierz task i wróć do głównego widoku
                        self.selected_index = list(self.tasks.values()).index(matching_tasks[current_index])
                        break
                    elif key == 27:  # ESC
                        break
            else:
                stdscr.addstr(3, 0, "No matching tasks found. Press any key to return...", 
                            curses.A_DIM)
                stdscr.refresh()
                stdscr.getch()

        curses.noecho()

    def delete_task(self, task_id):
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            # Usuń zależności
            cursor.execute('DELETE FROM dependencies WHERE task_id = ? OR dependency_id = ?', 
                         (task_id, task_id))
            # Usuń komentarze
            cursor.execute('DELETE FROM comments WHERE task_id = ?', (task_id,))
            # Usuń task
            cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            
        if task_id in self.tasks:
            del self.tasks[task_id]

    def delete_task_ui(self, stdscr):
        task = self.get_task_by_index(self.selected_index)
        if not task:
            return

        stdscr.clear()
        stdscr.addstr(0, 0, "Delete Task", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr(2, 0, f"Are you sure you want to delete task: ", curses.color_pair(5))
        stdscr.addstr(3, 2, f"{task.name}", curses.color_pair(1) | curses.A_BOLD)
        
        if task.dependencies:
            dep_names = [self.tasks[dep].name for dep in task.dependencies if dep in self.tasks]
            stdscr.addstr(4, 0, "Warning: This task has dependencies:", curses.color_pair(5))
            for idx, name in enumerate(dep_names):
                stdscr.addstr(5 + idx, 2, f"- {name}")

        # Sprawdź, czy jakieś taski zależą od tego taska
        dependent_tasks = []
        for t in self.tasks.values():
            if task.id in t.dependencies:
                dependent_tasks.append(t.name)

        if dependent_tasks:
            offset = 5 + (len(task.dependencies) if task.dependencies else 0)
            stdscr.addstr(offset, 0, "Warning: Other tasks depend on this task:", curses.color_pair(5))
            for idx, name in enumerate(dependent_tasks):
                stdscr.addstr(offset + 1 + idx, 2, f"- {name}")

        stdscr.addstr(stdscr.getmaxyx()[0]-2, 0, 
                     "Press Y to confirm deletion, any other key to cancel", 
                     curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()
        if key == ord('y') or key == ord('Y'):
            self.delete_task(task.id)
            self.selected_index = max(0, min(self.selected_index, len(self.tasks) - 1))
            
            stdscr.clear()
            stdscr.addstr(0, 0, "Task deleted successfully!", curses.color_pair(4) | curses.A_BOLD)
            stdscr.addstr(1, 0, "Press any key to continue...", curses.A_DIM)
            stdscr.refresh()
            stdscr.getch()

def main(stdscr):
    task_manager = TaskManager()
    task_manager.handle_input(stdscr)

if __name__ == "__main__":
    curses.wrapper(main)
