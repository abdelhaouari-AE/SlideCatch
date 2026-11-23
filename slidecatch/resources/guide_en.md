# SlideCatch — User guide

SlideCatch watches a presentation shared in Microsoft Teams (or any other program) and keeps a picture of every slide. At the end you check the slides and save them as a PowerPoint, a PDF or pictures.

## Quick start

1. **Choose what to capture.** Under *What to capture*, pick the meeting window (it is usually selected for you).
2. **Check the live preview.** The slide is outlined with a dashed line: only that part is kept.
3. **Name the session** (optional) and click **Start capture**. The main window hides and a small bar appears at the top of the screen.
4. When the presentation ends, click **Stop** on the bar. The review window opens.
5. Check the slides, then click **Export**.

## Choosing what to capture

**Window** (recommended for Teams)

- The meeting window may stay **behind other windows** while you work — but do not **minimize** it.
- SlideCatch finds the shared slide inside the window by itself and leaves out the chat, the toolbar and the video tiles (*Slide area, found automatically*).
- *Adjust area…* lets you draw the area yourself on a picture of the window. *Use full window* captures everything.

**Screen region**

- *Draw region on screen*, then drag a rectangle around the slide. Press **Esc** to cancel.
- The region must stay visible on the screen while capturing.

## During the capture

The small bar shows the time, the number of slides and the last slide.

| Button | Shortcut | What it does |
|---|---|---|
| Pause / Resume | Ctrl+Alt+P | Stops looking at the screen for a while |
| Camera | Ctrl+Alt+C | Captures the slide now, even if it barely changed |
| Stop | Ctrl+Alt+S | Ends the capture and opens the review |
| Arrow | — | Shows the main window |

The shortcuts work while Teams has the focus. The bar never appears in the slides, and you can drag it anywhere.

**Good to know**

- A new slide is kept about one second after it appears: SlideCatch waits until the picture is steady (end of a transition, shared screen sharp).
- Going back to an earlier slide does not add it twice.
- The mouse pointer and webcams are ignored.
- Every slide is saved on the disk the moment it is caught. If the computer stops, SlideCatch offers to restore the session at the next start.

## Review and export

- **Click** a slide to select it, **Ctrl+click** or **Shift+click** to select several.
- **Drag** slides to change their order, or use the arrows.
- **Crop** keeps only part of the selected slides. **Delete** (or the **Del** key) removes them.
- **Undo** / **Redo** (Ctrl+Z / Ctrl+Y) cancel any change.
- When a slide was built step by step (bullet after bullet), SlideCatch shows the steps and offers **Keep last step**.
- **Double-click** a slide to see it full size.

Export formats:

- **PowerPoint (.pptx)** — one slide per capture, with an optional title slide and the capture time in the speaker notes.
- **PDF** — one page per slide.
- **Pictures** — PNG files in a folder.

The captured pictures are never changed: crops, deletions and the order are applied when exporting.

## Settings (gear button)

- **Capture interval** — how often the screen is checked (1 second minimum).
- **Detection sensitivity** — *Low*: only clearly different slides; *Medium*: recommended; *High*: also each step of an animated slide.
- **Ignore the mouse pointer and video tiles** — recommended.
- **Merge animation steps automatically** — keeps only the last step of animated slides during the capture.
- **Shortcuts that work in any program**, **Theme** (light, dark, system), **Language**, **Session folder**.

## Problems?

| What you see | What to do |
|---|---|
| "The window is minimized" | Restore the window; it can stay behind others. |
| Too many similar slides | Lower the sensitivity, or adjust the area to leave out moving parts. |
| A slide is missing | Raise the sensitivity, or press Ctrl+Alt+C during the meeting. |
| Black preview | Choose *Screen region* and keep the meeting visible. |
| "The file is open in another program" | Close the PowerPoint or PDF, then export again. |

## Privacy

Everything stays on your computer. The only thing SlideCatch contacts is GitHub, to see whether a new version exists (you can turn this off in Settings), and it installs an update only when you click "Update now". Ask the presenter's permission before capturing, as you would before recording a meeting.

SlideCatch {APP_VERSION} — © {APP_YEAR} {APP_AUTHOR}
