"""
ignotext.py — one text box behaviour for the whole project.

Every field in ignoAPI used to be its own half of a text box: typing appended
to the end, backspace removed the last character, and the "cursor" was a bar
drawn after the text whether or not that was where you were typing. There was
no caret to move, so there was no way to fix a character in the middle of an
address without deleting back to it.

This is the model behind a real one. It owns TEXT, CARET and SELECTION, and
turns a pygame key event into the edit Windows would have made:

    left/right          move; with ctrl, by word; with shift, select
    home/end            line start/end (ctrl+home/end for the whole text)
    up/down             previous/next line (multi-line only)
    backspace/delete    the selection if there is one, else one char;
                        with ctrl, a whole word
    ctrl+a              select all
    ctrl+c / ctrl+x     copy / cut the selection
    ctrl+v              paste over the selection
    ctrl+z / ctrl+y     undo / redo
    typing              replaces the selection

Drawing stays with the caller -- this module has no idea what a font is --
but caret_x() and index_at_x() convert between a caret position and a pixel,
which is what a caller needs to draw the caret and to place it on a click.
"""

_WORD_STOP = ' \t\n,;:/\\|()[]{}<>"\'=+*&^%$#@!?'


class Editor:
    """Text with a caret and a selection.

    `sel` is the far end of the selection (the anchor); the near end is the
    caret. None means nothing is selected. Keeping it that way round means
    shift+arrow extends from where you started, which is what every other
    text box does.
    """

    MAX_UNDO = 200

    def __init__(self, text="", caret=None, multiline=False):
        self.text = str("" if text is None else text)
        self.caret = len(self.text) if caret is None else self._clamp(caret)
        self.sel = None
        self.multiline = bool(multiline)
        self._undo = []
        self._redo = []

    def _clamp(self, i):
        return max(0, min(int(i), len(self.text)))

    def set_text(self, text, keep_caret=False):
        """Replace the content. Used when the field is loaded from elsewhere."""
        text = str("" if text is None else text)
        if text == self.text:
            return
        self.text = text
        self.caret = self._clamp(self.caret) if keep_caret else len(text)
        self.sel = None

    def sel_range(self):
        """(start, end) of the selection, or None."""
        if self.sel is None or self.sel == self.caret:
            return None
        return (min(self.sel, self.caret), max(self.sel, self.caret))

    def selected_text(self):
        r = self.sel_range()
        return self.text[r[0]:r[1]] if r else ""

    def _snapshot(self):
        self._undo.append((self.text, self.caret, self.sel))
        if len(self._undo) > self.MAX_UNDO:
            self._undo.pop(0)
        self._redo.clear()

    def delete_selection(self):
        r = self.sel_range()
        if not r:
            return False
        self.text = self.text[:r[0]] + self.text[r[1]:]
        self.caret = r[0]
        self.sel = None
        return True

    def insert(self, s):
        """Type or paste. Replaces the selection, as everywhere else does."""
        if not s:
            return False
        if not self.multiline:
            s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        self._snapshot()
        self.delete_selection()
        self.text = self.text[:self.caret] + s + self.text[self.caret:]
        self.caret += len(s)
        self.sel = None
        return True

    def select_all(self):
        self.sel = 0
        self.caret = len(self.text)

    def _line_bounds(self, i):
        start = self.text.rfind("\n", 0, i) + 1
        end = self.text.find("\n", i)
        return (start, len(self.text) if end < 0 else end)

    def _word_left(self, i):
        i = self._clamp(i)
        while i > 0 and self.text[i - 1] in _WORD_STOP:
            i -= 1
        while i > 0 and self.text[i - 1] not in _WORD_STOP:
            i -= 1
        return i

    def _word_right(self, i):
        n = len(self.text)
        i = self._clamp(i)
        while i < n and self.text[i] in _WORD_STOP:
            i += 1
        while i < n and self.text[i] not in _WORD_STOP:
            i += 1
        return i

    def word_at(self, i):
        """(start, end) of the word under `i` — what a double-click selects."""
        n = len(self.text)
        i = self._clamp(i)
        if n == 0:
            return (0, 0)
        if i >= n or self.text[i] in _WORD_STOP:
            if i > 0 and self.text[i - 1] not in _WORD_STOP:
                i -= 1
            else:
                return (i, min(i + 1, n))
        a = i
        while a > 0 and self.text[a - 1] not in _WORD_STOP:
            a -= 1
        b = i
        while b < n and self.text[b] not in _WORD_STOP:
            b += 1
        return (a, b)

    def _move(self, to, extend):
        to = self._clamp(to)
        if extend:
            if self.sel is None:
                self.sel = self.caret
        else:
            self.sel = None
        self.caret = to

    def key(self, key, unicode_ch, ctrl, shift, clip_get, clip_set, K):
        """Apply one key press. Returns True if it was handled.

        `K` is the pygame key-constant namespace, passed in so this module
        does not import pygame -- which keeps it testable without a display.
        """
        if K is None:
            return False
        n = len(self.text)
        if ctrl and key == K.K_a:
            self.select_all()
            return True
        if ctrl and key in (K.K_c, K.K_x):
            sel = self.selected_text()
            if sel and clip_set:
                clip_set(sel)
            if key == K.K_x and sel:
                self._snapshot()
                self.delete_selection()
            return True
        if ctrl and key == K.K_v:
            if clip_get:
                self.insert(clip_get() or "")
            return True
        if ctrl and key == K.K_z:
            if self._undo:
                self._redo.append((self.text, self.caret, self.sel))
                self.text, self.caret, self.sel = self._undo.pop()
            return True
        if ctrl and key == K.K_y:
            if self._redo:
                self._undo.append((self.text, self.caret, self.sel))
                self.text, self.caret, self.sel = self._redo.pop()
            return True
        if key == K.K_LEFT:
            self._move(self._word_left(self.caret) if ctrl else self.caret - 1, shift)
            return True
        if key == K.K_RIGHT:
            self._move(self._word_right(self.caret) if ctrl else self.caret + 1, shift)
            return True
        if key == K.K_HOME:
            self._move(0 if ctrl else self._line_bounds(self.caret)[0], shift)
            return True
        if key == K.K_END:
            self._move(n if ctrl else self._line_bounds(self.caret)[1], shift)
            return True
        if key in (K.K_UP, K.K_DOWN) and self.multiline:
            start, end = self._line_bounds(self.caret)
            col = self.caret - start
            if key == K.K_UP:
                if start == 0:
                    self._move(0, shift)
                    return True
                p_start, p_end = self._line_bounds(start - 1)
                self._move(min(p_start + col, p_end), shift)
                return True
            else:
                if end >= n:
                    self._move(n, shift)
                    return True
                nx_start, nx_end = self._line_bounds(end + 1)
                self._move(min(nx_start + col, nx_end), shift)
                return True
        if key == K.K_BACKSPACE:
            if self.sel_range():
                self._snapshot()
                self.delete_selection()
                return True
            if self.caret > 0:
                self._snapshot()
                to = self._word_left(self.caret) if ctrl else self.caret - 1
                self.text = self.text[:to] + self.text[self.caret:]
                self.caret = to
            return True
        if key == K.K_DELETE:
            if self.sel_range():
                self._snapshot()
                self.delete_selection()
                return True
            if self.caret < n:
                self._snapshot()
                to = self._word_right(self.caret) if ctrl else self.caret + 1
                self.text = self.text[:self.caret] + self.text[to:]
            return True
        if key in (K.K_RETURN, K.K_KP_ENTER):
            if self.multiline:
                self.insert("\n")
                return True
            return False
        if key == K.K_TAB:
            return False
        if unicode_ch and unicode_ch.isprintable():
            self.insert(unicode_ch)
            return True
        return False

    def caret_x(self, measure, caret=None):
        """Pixel offset of the caret. `measure` turns text into a width."""
        i = self.caret if caret is None else self._clamp(caret)
        start = self._line_bounds(i)[0] if self.multiline else 0
        return measure(self.text[start:i])

    def index_at_x(self, measure, x, line_start=0, line_end=None):
        """Which caret position a click at pixel `x` lands on.

        Rounds to the NEAREST gap between characters, not the one before --
        clicking the right half of a character should put the caret after it,
        which is what makes click-to-position feel right.
        """
        if line_end is None:
            line_end = len(self.text)
        best = line_start
        best_d = abs(x)
        for i in range(line_start, line_end + 1):
            d = abs(measure(self.text[line_start:i]) - x)
            if d < best_d:
                best = i
                best_d = d
        return best


def to_lines(value, sep=','):
    """'a, b ,c' -> 'a\\nb\\nc' — a list as one entry per line."""
    parts = [p.strip() for p in str(value or '').replace(';', sep).split(sep)]
    return '\n'.join(p for p in parts if p)


def from_lines(text, sep=', '):
    """The inverse. Blank lines are dropped, so pressing Enter twice while
    editing does not leave an empty entry that later parses as a blank host."""
    parts = [p.strip() for p in str(text or '').splitlines()]
    return sep.join(p for p in parts if p)
