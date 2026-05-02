# ffrich Future Improvements

This document tracks planned and suggested improvements for the `ffrich` tool.

## Technical Improvements
- [ ] **Argparse Integration**:
    - [ ] Add a proper `--help` message and `--version` flag.
    - [ ] Support toggling features (e.g., `--no-color`, `--simple-progress`, `--verbose`).
- [ ] **Improved FPS Logic**:
    - [ ] Detect when FPS parsing fails and avoid showing "1.0 fps" (which is actually 1.0 seconds per second).
    - [ ] Hide the FPS column or label it correctly when not processing frames.
- [ ] **Handling Multiple Outputs**:
    - [ ] Update `_DEST_RX` to handle multiple destination files.
    - [ ] Improve UI to show progress for multiple simultaneous transcodes.
- [ ] **Interactive Prompts**:
    - [ ] Move beyond the hardcoded `[y/N]` check to a more flexible prompt detection system.
    - [ ] Support custom plugin prompts.

## Performance & UX
- [ ] **Refine Buffered Reading**: Fine-tune buffer sizes for different workloads if necessary.
- [ ] **Dynamic Column Sizing**: Ensure the progress bar remains readable on very narrow terminals.
