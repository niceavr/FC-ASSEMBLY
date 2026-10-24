# FC-ASSEMBLY

[![License: MIT](https://img.shields.io/github/license/niceavr/FC-ASSEMBLY)](LICENSE)

A projector-based work guidance demo for assembly stations, plus a collection of small C and Python practice programs.

## Work guidance apps (Python / tkinter)

These apps draw a simulated worktable with work areas and highlight the current assembly step, so the screen can be projected onto a real table.

| File | Description |
| --- | --- |
| `s1.py` | Basic version: 3 steps (pick spanner, assemble cable, inspect) on a white background. |
| `darkmode.py` | Dark-mode version of the 3-step guide with blinking, color-coded active boxes. |
| `darkmode1.py` | 6-bin version that also plays a video for each step (`one.mp4`, `two.mp4`, `three.mp4`, ...). |

### Requirements

- Python 3 with tkinter
- For `darkmode1.py`: `opencv-python` and `Pillow`

```
pip install -r requirements.txt
```

### Running

```
python darkmode1.py
```

### Controls

| Key | Action |
| --- | --- |
| Space / Right arrow | Next step |
| Left arrow | Previous step |
| F11 | Toggle fullscreen (`s1.py`, `darkmode.py`) |
| Escape | Exit fullscreen (`darkmode1.py`: close the app) |

`darkmode1.py` expects six videos, but only `one.mp4`, `two.mp4` and `three.mp4` are included.

## C practice programs

Compile with any C compiler, e.g. `gcc a1.cpp -o a1`. Prebuilt Windows `.exe` files are included.

| File | Description |
| --- | --- |
| `a1.cpp` | Electricity bill from current and previous meter readings, using slab rates. |
| `a2.cpp` | Checks whether a number is positive, negative or zero. |
| `a3.cpp` | Checks whether a person is eligible to vote. |
| `prog1.cpp` | Discount and net amount for a purchase (30% at 5000 or more, otherwise 10%). |
| `Untitled1.cpp` | Counts the factors of a number and checks whether it is prime. |

## Python practice programs

| File | Description |
| --- | --- |
| `arith.py` | Prints even numbers up to n. |
| `number.py` | Maps a number to a day of the week. |
| `leka.py` | Single inheritance demo (`Student` → `Teacher`). |
| `prog1.py` | Multilevel inheritance demo (`Square` → `Rect` → `Box`). |
| `prog2.py` | Constructor with arguments demo. |

## Other files

- `b.txt`, `charan.txt`, `charan1.txt`, `data`, `sample`, `stu`, `student`, `test`: sample text and data files used by file-handling exercises.
- `EX1.xlsx`, `girl.jpg`, `reflection_out.jpg`: sample spreadsheet and images.

## License

MIT. See [LICENSE](LICENSE).
