# L2 → L1 Translation Task (Browser)

Run `index.html` in a modern browser (offline OK). Audio is loaded locally from `Target_Stimuli/{female|male}/{word}.mp3`. Each of the 24 words is presented twice: even IDs hear female then male; odd IDs hear male then female.

## How to run
- Enter a participant ID and click “プリロード開始” to generate the order and preload all audio; grant microphone access when prompted.
- After preload, press the space bar to start. The cursor hides during the task. Key presses do not advance trials; timing is fixed.
- At the end, a zip downloads automatically with the CSV and all WAV recordings.

## Trial structure and timing
- 48 trials total (24 words × 2 attempts: attempt 1 = first-voice, attempt 2 = second-voice).
- Per trial: show sound icon → play audio immediately; record for 6 s → ITI 1.5 s with fixation.
- Order: the 24 words are seeded-shuffled by participant ID; the same order is repeated for attempt 2 with the opposite voice.

## Condition logic (ID parity)
- Even ID: attempt 1 = female, attempt 2 = male.
- Odd ID: attempt 1 = male, attempt 2 = female.

## Outputs (zip)
- `results_{participantId}.csv` with columns: `trial,attempt,voice,word,word_id,list,audio_file,playback_onset_ms,recording_start_ms,recording_end_ms,iti_ms,participant_id` (times in ms from task start).
- One WAV per trial: `{participantId}_trial{N}_{voice}_{word}.wav` (accents stripped in filename).

## Requirements
- Browser with Web Audio + getUserMedia (Chrome/Firefox etc.).
- Microphone permission granted; speakers/headphones for audio playback.  
