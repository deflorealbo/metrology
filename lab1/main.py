"""
Расчёт метрик Холстеда для кода на Ruby.
Патчи A-R.
"""
import re
import math
from collections import Counter

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


BLOCK_OPENERS = {
    'if', 'unless', 'case', 'while', 'until', 'for',
    'def', 'class', 'module', 'begin', 'do', 'loop',
}
MODIFIER_KEYWORDS = {'if', 'unless', 'while', 'until'}
CONTROL_KEYWORDS = {
    'return', 'yield', 'break', 'next', 'redo', 'retry',
    'super', 'raise', 'throw', 'catch',
}
BUILTIN_METHODS = {
    'puts', 'print', 'gets', 'require', 'require_relative', 'include',
    'extend', 'attr_accessor', 'attr_reader', 'attr_writer', 'attr',
    'p', 'pp', 'raise', 'fail', 'lambda', 'proc', 'loop', 'exit',
    'abort', 'sleep', 'rand', 'srand', 'format', 'sprintf', 'printf',
    'open', 'read', 'write', 'system', 'exec', 'spawn', 'load', 'defined?',
}
# ПАТЧ R: puts/print/gets никогда не считаются аргументами
ALWAYS_OPERATOR_BUILTINS = {'puts', 'print', 'gets', 'require',
                            'require_relative', 'raise', 'fail', 'p'}

NON_OPERANDS = BLOCK_OPENERS | CONTROL_KEYWORDS | BUILTIN_METHODS | {
    'end', 'else', 'elsif', 'when', 'then', 'rescue', 'ensure',
    'in', 'do', 'and', 'or', 'not',
}
IGNORED_KEYWORDS = {
    'end', 'else', 'elsif', 'when', 'then', 'rescue', 'ensure',
    'in', 'do',
}
SYMBOL_OPERATORS = [
    '<=>', '===', '**=', '<<=', '>>=', '&&=', '||=', '...', '..',
    '<=', '>=', '==', '!=', '+=', '-=', '*=', '/=', '%=', '**',
    '<<', '>>', '&&', '||', '::', '=>', '->', '&=', '|=', '^=',
    '=~', '!~',
    '+', '-', '*', '/', '%', '<', '>', '=', '!', '&', '|', '^', '~',
    '?', ':', ';', ',', '.',
]
RE_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*[!?]?')
RE_NUMBER = re.compile(r'\d+(?:\.\d+)?(?:[eE][+-]?\d+)?')
RE_SYMBOL_LIT = re.compile(r':[A-Za-z_][A-Za-z0-9_]*[!?]?')
RE_LABEL = re.compile(r'^[ \t]*[A-Za-z_][A-Za-z0-9_]*:[ \t]*$', re.M)

STR_START = '__STR_START__'
STR_END = '__STR_END__'
INTERP_START = '__INTERP_START__'
INTERP_END = '__INTERP_END__'

# ПАТЧ R: известные переменные (параметры + левые части присваиваний)
PARAM_NAMES = set()


def clean_code(code: str) -> str:
    out = []
    i, n = 0, len(code)
    while i < n:
        if code.startswith('=begin', i):
            end = code.find('=end', i)
            i = (end + 4) if end != -1 else n
            continue
        c = code[i]
        if c == '#':
            while i < n and code[i] != '\n':
                i += 1
            continue
        if c in ('"', "'"):
            quote = c
            i += 1
            whole_text = []
            interpolations = []
            while i < n:
                if code[i] == '\\' and i + 1 < n:
                    whole_text.append('\\')
                    whole_text.append(code[i + 1])
                    i += 2
                    continue
                if quote == '"' and code.startswith('#{', i):
                    whole_text.append(' ')
                    depth = 1
                    j = i + 2
                    start = j
                    while j < n and depth > 0:
                        if code[j] == '{':
                            depth += 1
                        elif code[j] == '}':
                            depth -= 1
                            if depth == 0:
                                break
                        j += 1
                    inner = code[start:j]
                    interpolations.append(inner)
                    i = j + 1
                    continue
                if code[i] == quote:
                    i += 1
                    break
                whole_text.append(code[i])
                i += 1
            text = ''.join(whole_text)
            out.append(' ' + STR_START + quote + text + quote + STR_END + ' ')
            for inner in interpolations:
                out.append(' ' + INTERP_START + ' '
                           + clean_code(inner)
                           + ' ' + INTERP_END + ' ')
            continue
        out.append(c)
        i += 1
    text = ''.join(out)
    text = RE_LABEL.sub('', text)
    return text


def tokenize(code: str):
    tokens = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if c in ' \t\r':
            i += 1
            continue
        if c == '\n':
            tokens.append(('newline', '\n'))
            i += 1
            continue
        if code.startswith(INTERP_START, i):
            tokens.append(('interp_open', '#{'))
            i += len(INTERP_START)
            continue
        if code.startswith(INTERP_END, i):
            tokens.append(('interp_close', '}'))
            i += len(INTERP_END)
            continue
        if code.startswith(STR_START, i):
            start = i + len(STR_START)
            end = code.find(STR_END, start)
            if end == -1:
                end = n
            text = code[start:end]
            tokens.append(('string', text))
            i = end + len(STR_END)
            continue

        # ПАТЧ B: унарный минус — часть числа
        if c == '-' and i + 1 < n and code[i + 1].isdigit():
            prev_is_operand = False
            if tokens:
                pk, pv = tokens[-1]
                if pk in ('ident', 'number', 'string', 'symbol'):
                    if not (pk == 'ident' and pv in (
                            'return', 'when', 'then', 'if', 'unless',
                            'while', 'until', 'and', 'or', 'not',
                            'case', 'else', 'elsif')):
                        prev_is_operand = True
                elif (pk, pv) in (('punct', ')'), ('punct', ']'),
                                   ('punct', '}')):
                    prev_is_operand = True
            if not prev_is_operand:
                m = RE_NUMBER.match(code, i + 1)
                if m:
                    tokens.append(('number', '-' + m.group(0)))
                    i = m.end()
                    continue

        m = RE_SYMBOL_LIT.match(code, i)
        if m:
            tokens.append(('symbol', m.group(0)))
            i = m.end()
            continue
        m = RE_NUMBER.match(code, i)
        if m:
            tokens.append(('number', m.group(0)))
            i = m.end()
            continue
        m = RE_IDENT.match(code, i)
        if m:
            tokens.append(('ident', m.group(0)))
            i = m.end()
            continue
        matched = False
        for op in SYMBOL_OPERATORS:
            if code.startswith(op, i):
                tokens.append(('op', op))
                i += len(op)
                matched = True
                break
        if matched:
            continue
        tokens.append(('punct', c))
        i += 1
    return tokens


def _is_modifier(tokens, idx):
    val = tokens[idx][1]
    if val not in MODIFIER_KEYWORDS:
        return False
    j = idx - 1
    has_sig_before = False
    while j >= 0:
        kind, v = tokens[j]
        if kind == 'newline':
            break
        if kind == 'ident' and v in BLOCK_OPENERS and not has_sig_before:
            return False
        if kind in ('ident', 'number', 'string', 'symbol', 'op', 'punct'):
            has_sig_before = True
        j -= 1
    return has_sig_before


def _is_method_call(sig, idx, at_line_start, line_start_idx):
    if sig[idx][0] != 'ident':
        return False
    name = sig[idx][1]
    if name in NON_OPERANDS or name in IGNORED_KEYWORDS:
        return False
    # ПАТЧ R: известные переменные — не вызовы
    if name in PARAM_NAMES:
        return False
    if name.endswith('?') or name.endswith('!'):
        return True
    if idx > 0 and sig[idx - 1] in (('op', '.'), ('punct', '.')):
        return True
    if idx + 1 < len(sig) and sig[idx + 1] in (('punct', '('), ('op', '(')):
        return True
    if idx + 1 < len(sig):
        nxt = sig[idx + 1]
        if nxt[0] in ('ident', 'number', 'string', 'symbol'):
            if idx + 2 < len(sig) and sig[idx + 2] == ('op', '='):
                return False
            if idx == 0:
                return True
            prev = sig[idx - 1]
            if prev in (('op', '='), ('op', '=>')):
                return False
            if prev[0] == 'op' and prev[1] in (
                    '=', '=>', ',', '|', '[', '(', '{'):
                return False
            if prev[0] == 'punct' and prev[1] in ('(', '[', '{'):
                return False
            if prev[0] == 'ident' and prev[1] not in NON_OPERANDS:
                return True
            if prev[0] in ('op', 'punct'):
                return True
    if at_line_start:
        if idx + 1 < len(sig) and sig[idx + 1] == ('op', '='):
            return False
        if idx > 0 and sig[idx - 1][0] == 'ident' and sig[idx - 1][1] in (
                'def', 'class', 'module'):
            return False
        if idx > 0 and sig[idx - 1] == ('op', '|'):
            return False
        if idx + 1 >= len(sig) or (idx + 1) in line_start_idx:
            return True
        if idx + 1 < len(sig) and sig[idx + 1][0] == 'ident' and \
                sig[idx + 1][1] in IGNORED_KEYWORDS:
            return True
    return False


def _orig_index(tokens, sig, i):
    k = 0
    for j, t in enumerate(tokens):
        if t[0] == 'newline':
            continue
        if k == i:
            return j
        k += 1
    return len(tokens) - 1


def parse(tokens):
    operators = []
    operands = []

    sig = []
    line_start_idx = set()
    for t in tokens:
        if t[0] == 'newline':
            line_start_idx.add(len(sig))
        else:
            sig.append(t)

    n = len(sig)
    i = 0
    while i < n:
        kind, val = sig[i]
        at_line_start = (i in line_start_idx) or (i == 0)

        # ПАТЧ H: интерполяция — отдельный оператор #{}
        if kind == 'interp_open':
            operators.append('#{}')
            i += 1
            continue
        if kind == 'interp_close':
            i += 1
            continue

        if kind in ('string', 'number', 'symbol'):
            operands.append(val)
            i += 1
            continue

        if kind == 'ident':
            if val in IGNORED_KEYWORDS:
                i += 1
                continue
            if val in ('nil', 'true', 'false'):
                operands.append(val)
                i += 1
                continue

            if val in BLOCK_OPENERS:
                if val in MODIFIER_KEYWORDS and _is_modifier(
                        tokens, _orig_index(tokens, sig, i)):
                    operators.append(val)
                    i += 1
                    continue
                operators.append(f"{val}..end")
                i += 1
                if val in ('def', 'class', 'module'):
                    if i < n and sig[i][0] == 'ident':
                        operators.append(sig[i][1])
                        i += 1
                    # ПАТЧ E + N: параметры метода — операнды, запятые — операторы
                    if i < n and sig[i] in (('punct', '('), ('op', '(')):
                        i += 1
                        depth = 1
                        while i < n and depth > 0:
                            t = sig[i]
                            if t in (('punct', '('), ('op', '(')):
                                depth += 1
                                i += 1
                                continue
                            if t in (('punct', ')'), ('op', ')')):
                                depth -= 1
                                i += 1
                                continue
                            if depth == 1:
                                if t[0] in ('ident', 'number',
                                            'string', 'symbol'):
                                    operands.append(t[1])
                                    if t[0] == 'ident':
                                        PARAM_NAMES.add(t[1])
                                elif t == ('op', ','):
                                    operators.append(',')
                            i += 1
                        continue
                continue

            if val in CONTROL_KEYWORDS:
                operators.append(val)
                i += 1
                continue

            # ПАТЧ J + L + R: builtin — проверяем позицию
            if val in BUILTIN_METHODS:
                if val in ALWAYS_OPERATOR_BUILTINS:
                    operators.append(val)
                    i += 1
                    if i < n and sig[i] in (('punct', '('), ('op', '(')):
                        i += 1
                    continue
                prev = sig[i - 1] if i > 0 else None
                is_argument_position = (
                    prev is not None and (
                        (prev[0] == 'op' and prev[1] in (
                            '=', '=>', ',', '|', '[', '(', '{', '+', '-',
                            '*', '/', '%', '<', '>', '==', '!=', '<=',
                            '>=', '&&', '||', '<<', '>>', '**')) or
                        (prev[0] == 'punct' and prev[1] in ('(', '[', '{'))
                    )
                )
                if is_argument_position:
                    operands.append(val)
                    i += 1
                    continue
                operators.append(val)
                i += 1
                if i < n and sig[i] in (('punct', '('), ('op', '(')):
                    i += 1
                continue

            # ПАТЧ J: обычный метод — НЕ пропускаем аргументы
            if _is_method_call(sig, i, at_line_start, line_start_idx):
                operators.append(val)
                if i + 1 < n and sig[i + 1] in (('punct', '('), ('op', '(')):
                    i += 2
                else:
                    i += 1
                continue
            else:
                operands.append(val)
                # ПАТЧ R: левая часть присваивания → запоминаем как переменную
                if i + 1 < n and sig[i + 1] in (
                        ('op', '='), ('op', '+='), ('op', '-='),
                        ('op', '*='), ('op', '/='), ('op', '%='),
                        ('op', '**='), ('op', '||='), ('op', '&&='),
                        ('op', '<<=')):
                    PARAM_NAMES.add(val)
                i += 1
                continue

        if kind == 'op':
            # ПАТЧ C+G+N: |x, y| — оператор, параметры — операнды,
            # запятые внутри — операторы
            if val == '|':
                j = i + 1
                found = False
                while j < n and sig[j][0] != 'newline':
                    if sig[j] == ('op', '|'):
                        found = True
                        break
                    j += 1
                if found:
                    operators.append('|...|')
                    for k in range(i + 1, j):
                        if sig[k][0] == 'ident':
                            operands.append(sig[k][1])
                            PARAM_NAMES.add(sig[k][1])
                        elif sig[k] == ('op', ','):
                            operators.append(',')
                    i = j + 1
                    continue
                operators.append(val)
                i += 1
                continue

            # ПАТЧ A + P: тернарный ? : — один оператор,
            # содержимое НЕ съедается, ':' не считается
            if val == '?':
                operators.append('? :')
                i += 1
                continue

            if val == ':':
                # ':' не оператор (либо хэш-ключ, либо часть ? :)
                i += 1
                continue

            operators.append(val)
            i += 1
            continue

        if kind == 'punct':
            # ПАТЧ Q: ( ) — оператор, содержимое НЕ съедается
            if val == '(':
                is_group = True
                if i > 0:
                    prev = sig[i - 1]
                    if prev[0] == 'ident' and prev[1] not in NON_OPERANDS:
                        is_group = False
                    elif prev in (('op', '.'), ('punct', '.')):
                        is_group = False
                if is_group:
                    operators.append('( )')
                    i += 1
                    continue
                else:
                    i += 1
                    continue
            if val == ')':
                i += 1
                continue
            if val == '[':
                operators.append('[ ]')
                i += 1
                continue
            if val == ']':
                i += 1
                continue
            if val == '{':
                operators.append('{ }')
                i += 1
                continue
            if val == '}':
                i += 1
                continue
            if val in (';', '.'):
                operators.append(val)
                i += 1
                continue
            i += 1
            continue

        i += 1

    return operators, operands


def skip_parens(sig, i):
    depth = 0
    n = len(sig)
    while i < n:
        t = sig[i]
        if t in (('punct', '('), ('op', '(')):
            depth += 1
        elif t in (('punct', ')'), ('op', ')')):
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def holstead_metrics(code: str):
    global PARAM_NAMES
    PARAM_NAMES = set()
    cleaned = clean_code(code)
    tokens = tokenize(cleaned)
    operators, operands = parse(tokens)
    op_freq = Counter(operators)
    operand_freq = Counter(operands)
    eta1 = len(op_freq)
    eta2 = len(operand_freq)
    N1 = sum(op_freq.values())
    N2 = sum(operand_freq.values())
    eta = eta1 + eta2
    N = N1 + N2
    V = N * math.log2(eta) if eta > 1 else 0.0
    return {
        'operators': dict(op_freq),
        'operands': dict(operand_freq),
        'eta1': eta1, 'eta2': eta2,
        'N1': N1, 'N2': N2,
        'eta': eta, 'N': N, 'V': V,
    }


# ===========================================================
#                          GUI
# ===========================================================

class HolsteadApp:
    def __init__(self, root):
        self.root = root
        root.title("Метрики Холстеда для Ruby")
        root.geometry("1200x750")
        top = ttk.Frame(root, padding=5)
        top.pack(fill=tk.X)
        ttk.Button(top, text="Открыть файл Ruby...",
                   command=self.open_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Анализировать",
                   command=self.analyze).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Очистить",
                   command=self.clear).pack(side=tk.LEFT, padx=5)
        paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        left = ttk.Frame(paned)
        paned.add(left, weight=1)
        ttk.Label(left, text="Исходный код Ruby:").pack(anchor=tk.W)
        self.code_text = tk.Text(left, wrap=tk.NONE, font=("Consolas", 10))
        self.code_text.pack(fill=tk.BOTH, expand=True)
        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        ttk.Label(right, text="Базовые метрики (6):").pack(anchor=tk.W)
        cols = ("j", "Оператор", "f1j", "i", "Операнд", "f2i")
        self.base_tree = ttk.Treeview(right, columns=cols,
                                       show="headings", height=18)
        for c, w in zip(cols, (40, 180, 50, 40, 180, 50)):
            self.base_tree.heading(c, text=c)
            self.base_tree.column(c, width=w, anchor=tk.CENTER)
        self.base_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.base_totals = ttk.Label(right, text="", font=("Consolas", 10))
        self.base_totals.pack(anchor=tk.W, pady=5)
        ttk.Label(right, text="Расширенные метрики (3):").pack(
            anchor=tk.W, pady=(10, 0))
        self.ext_label = ttk.Label(right, text="", font=("Consolas", 11),
                                    justify=tk.LEFT)
        self.ext_label.pack(anchor=tk.W, pady=5)

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Выберите файл Ruby",
            filetypes=[("Ruby files", "*.rb"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Ошибка",
                                 f"Не удалось прочитать файл:\n{e}")
            return
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert("1.0", content)

    def clear(self):
        self.code_text.delete("1.0", tk.END)
        for row in self.base_tree.get_children():
            self.base_tree.delete(row)
        self.base_totals.config(text="")
        self.ext_label.config(text="")

    def analyze(self):
        code = self.code_text.get("1.0", tk.END)
        if not code.strip():
            messagebox.showwarning("Внимание",
                                   "Введите или загрузите код Ruby.")
            return
        try:
            m = holstead_metrics(code)
        except Exception as e:
            messagebox.showerror("Ошибка анализа", str(e))
            return
        for row in self.base_tree.get_children():
            self.base_tree.delete(row)
        op_items = sorted(m['operators'].items(),
                          key=lambda x: (-x[1], x[0]))
        operand_items = sorted(m['operands'].items(),
                               key=lambda x: (-x[1], x[0]))
        max_len = max(len(op_items), len(operand_items))
        for idx in range(max_len):
            j = str(idx + 1) if idx < len(op_items) else ""
            op = op_items[idx][0] if idx < len(op_items) else ""
            f1 = str(op_items[idx][1]) if idx < len(op_items) else ""
            i_ = str(idx + 1) if idx < len(operand_items) else ""
            od = operand_items[idx][0] if idx < len(operand_items) else ""
            f2 = str(operand_items[idx][1]) if idx < len(operand_items) else ""
            self.base_tree.insert("", tk.END,
                                  values=(j, op, f1, i_, od, f2))
        self.base_totals.config(
            text=(f"η1 = {m['eta1']}   N1 = {m['N1']}    "
                  f"η2 = {m['eta2']}   N2 = {m['N2']}"))
        self.ext_label.config(
            text=(f"Словарь программы  η = η1 + η2 = "
                  f"{m['eta1']} + {m['eta2']} = {m['eta']}\n"
                  f"Длина программы    N = N1 + N2 = "
                  f"{m['N1']} + {m['N2']} = {m['N']}\n"
                  f"Объём программы    V = N · log2(η) = "
                  f"{m['N']} · log2({m['eta']}) ≈ {m['V']:.2f}"))


if __name__ == "__main__":
    root = tk.Tk()
    app = HolsteadApp(root)
    root.mainloop()