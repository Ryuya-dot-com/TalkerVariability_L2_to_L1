# L2 → L1 Translation Task (Browser)

Runs offline in a modern browser. Open `index.html`. Audio is loaded from `Target_Stimuli/{female|male}/{word}.mp3`. Each of the 24 words is presented twice; talker order depends on participant ID parity.

## How to run
- Open `index.html` in Chrome/Firefox. Enter a participant ID and click “プリロード開始” to build the schedule and preload audio; allow mic access.
- After preload, press the space bar to start. Cursor hides. Keys do not advance trials (only timing drives progress).
- When the session ends, a ZIP auto-downloads containing the CSV and WAVs.

## Trial structure and timing
- 48 trials (24 words × 2 attempts). Attempt 1 uses the first voice, attempt 2 uses the opposite voice.
- Per trial: show sound icon → play audio immediately; record for 6 s → ITI 1.5 s with fixation.
- Order: participant-ID–seeded shuffle of 24 words; the same order is repeated for attempt 2.

## Condition logic (ID parity)
- Even ID: attempt 1 = female, attempt 2 = male.
- Odd ID: attempt 1 = male, attempt 2 = female.

## Output (per run, ZIP)
- `results_{participantId}.csv` columns:  
  - `trial, attempt, voice, word, word_id, list, audio_file`  
  - `trial_start_epoch_ms`  
  - `playback_onset_ms, playback_end_ms` (ms from trial start)  
  - `recording_start_ms, recording_end_ms` (ms from trial start)  
  - `recording_start_epoch_ms, recording_end_epoch_ms`  
  - `iti_ms, participant_id`  
  - Notes: WAVs include both the stimulus and the participant’s speech; playback timings are per-trial (not cumulative).
- WAV per trial: `{participantId}_trial{N}_{voice}_{word}.wav` (accents stripped).

## Latency analysis (`Results/analyze_latency.py`)
- Usage (from repo root):  
  ```bash
  /usr/bin/python3 Experiment/L2_to_L1/Results/analyze_latency.py \
    --root ./Experiment/L2_to_L1/Results/l2_to_l1_XXX
  ```
  Finds `results_*.csv` and WAVs in `root`, writes `latency_summary.csv`, and saves QC plots to `root/qc_plots` by default.
- Key options: `--threshold-db` (default -40), `--guard-ms` (default 50), `--frame-ms`, `--min-frames`. Lower threshold or shorter guard if speech is very quiet/early.
- Output columns add: `latency_ms_from_playback_end`, `onset_ms_from_recording_start`, `playback_end_ms_rel`, `dynamic_threshold_db`, `fallback_used`, plus status/notes.

## Requirements
- Browser with Web Audio + getUserMedia (Chrome/Firefox).
- Mic permission granted; speakers/headphones for audio playback.  
