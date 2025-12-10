#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L2-to-L1 taskの録音から発話潜時を自動計測するスクリプト。

実行の前提:
- 同じディレクトリに results_*.csv と WAV (例: 999_trial1_male_sandia.wav) がある。
- CSV には playback_end_ms が含まれており、録音には「提示音声 + 参加者の発話」が混在している。

出力:
- latency_ms_from_playback_end: 再生終了から発話開始までの潜時 (ms)
- onset_ms_from_recording_start: 録音開始から発話開始までの時刻 (ms)
"""

import argparse
import glob
import math
import os
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import soundfile as sf


def strip_accents(text: str) -> str:
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="L2→L1 発話潜時解析ツール")
    parser.add_argument(
        "--root",
        type=str,
        default=".",
        help="results_*.csv と WAV が置かれているディレクトリ (default: current dir)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="結果CSVのパス（未指定なら root 配下の results_*.csv を自動検索）",
    )
    parser.add_argument(
        "--threshold-db",
        type=float,
        default=-40.0,
        help="発話判定に用いるエネルギー閾値[dB] (default: -40)",
    )
    parser.add_argument(
        "--frame-ms",
        type=float,
        default=10.0,
        help="移動平均エネルギーのフレーム長[ms] (default: 10)",
    )
    parser.add_argument(
        "--min-frames",
        type=int,
        default=4,
        help="閾値連続超過が必要なフレーム数 (default: 4)",
    )
    parser.add_argument(
        "--guard-ms",
        type=float,
        default=50.0,
        help="playback_end_ms からさらに無視するガード時間[ms] (default: 50)",
    )
    parser.add_argument(
        "--save-plots",
        type=str,
        default=None,
        help="検出結果のQCプロットを書き出すディレクトリ（未指定なら root/qc_plots に保存）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="出力CSVパス (default: <root>/latency_summary.csv)",
    )
    return parser.parse_args()


def rolling_energy_db(signal: np.ndarray, sample_rate: int, frame_ms: float) -> Tuple[np.ndarray, int]:
    frame_length = max(1, int(round(sample_rate * frame_ms / 1000.0)))
    window = np.ones(frame_length, dtype=np.float32) / frame_length
    energy = np.convolve(np.square(signal, dtype=np.float32), window, mode="valid")
    energy_db = 10.0 * np.log10(np.maximum(energy, 1e-12))
    return energy_db, frame_length


def detect_onset_after(
    energy_db: np.ndarray,
    sample_rate: int,
    frame_length: int,
    start_ms: float,
    threshold_db: float,
    min_frames: int,
) -> Optional[float]:
    """start_ms 以降での発話開始時刻(ms, 録音頭基準)を返す。energy_db はモノラル化/平滑化済み。"""
    start_sample = int(round(start_ms / 1000.0 * sample_rate))
    start_idx = min(len(energy_db), max(0, start_sample))

    above = energy_db[start_idx:] > threshold_db
    onset_idx = None
    for i in range(len(above)):
        if not above[i]:
            continue
        if i + min_frames > len(above):
            break
        if np.all(above[i : i + min_frames]):
            onset_idx = start_idx + i
            break

    if onset_idx is None:
        return None

    latency_samples = onset_idx + frame_length / 2.0
    onset_ms = latency_samples / sample_rate * 1000.0
    return onset_ms


def find_results_csv(root: str, csv_arg: Optional[str]) -> str:
    if csv_arg:
        if not os.path.isfile(csv_arg):
            raise FileNotFoundError(f"CSV not found: {csv_arg}")
        return os.path.abspath(csv_arg)
    candidates = sorted(glob.glob(os.path.join(root, "results_*.csv")))
    if not candidates:
        raise FileNotFoundError(f"results_*.csv が見つかりません: {root}")
    if len(candidates) > 1:
        raise RuntimeError(f"results_*.csv が複数見つかりました。--csv で指定してください: {candidates}")
    return os.path.abspath(candidates[0])


def build_wav_path(row: pd.Series, wav_dir: str) -> str:
    if "recording_file" in row and isinstance(row["recording_file"], str) and row["recording_file"]:
        return os.path.join(wav_dir, row["recording_file"])
    pid = str(row.get("participant_id", "")).strip()
    trial = str(row.get("trial", "")).strip()
    voice = str(row.get("voice", "")).strip().lower()
    word_raw = str(row.get("word", "")).strip()
    word = strip_accents(word_raw)
    filename = f"{pid}_trial{trial}_{voice}_{word}.wav"
    return os.path.join(wav_dir, filename)


def analyze(
    root: str,
    csv_path: str,
    threshold_db: float,
    frame_ms: float,
    min_frames: int,
    guard_ms: float,
    save_plots: Optional[str],
) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    wav_dir = os.path.abspath(root)
    records = []

    if save_plots:
        save_plots_dir = os.path.abspath(save_plots)
    else:
        save_plots_dir = os.path.join(wav_dir, "qc_plots")
    os.makedirs(save_plots_dir, exist_ok=True)

    for _, row in df.iterrows():
        wav_path = build_wav_path(row, wav_dir)
        result = row.to_dict()
        result.update(
            {
                "audio_path": wav_path,
                "playback_end_ms_rel": None,
                "latency_ms_from_playback_end": None,
                "onset_ms_from_recording_start": None,
                "max_energy_db": None,
                "median_energy_db": None,
                "status": "ok",
                "note": "",
            }
        )

        if not os.path.isfile(wav_path):
            result["status"] = "missing"
            result["note"] = "WAV not found"
            records.append(result)
            continue

        try:
            signal, sample_rate = sf.read(wav_path, always_2d=False)
        except Exception as error:
            result["status"] = "read_error"
            result["note"] = f"read error: {error}"
            records.append(result)
            continue

        if signal.ndim > 1:
            signal = np.mean(signal, axis=1)

        energy_db, frame_length = rolling_energy_db(signal, sample_rate, frame_ms)

        playback_end_abs = float(row.get("playback_end_ms", 0.0))
        rec_start_abs = float(row.get("recording_start_ms", 0.0))
        playback_end_rel = max(0.0, playback_end_abs - rec_start_abs)
        result["playback_end_ms_rel"] = playback_end_rel
        start_ms = playback_end_rel + guard_ms

        onset_ms = detect_onset_after(
            energy_db=energy_db,
            sample_rate=sample_rate,
            frame_length=frame_length,
            start_ms=start_ms,
            threshold_db=threshold_db,
            min_frames=min_frames,
        )

        # fallback: adaptive threshold based on pre-playback noise if needed
        fallback_used = False
        dynamic_threshold = threshold_db
        pre_region = energy_db[: int(max(1, playback_end_rel / 1000.0 * sample_rate))]
        if onset_ms is None and pre_region.size > 0:
            fallback_used = True
            noise_db = float(np.percentile(pre_region, 75))
            dynamic_threshold = max(threshold_db - 5.0, noise_db + 6.0)
            onset_ms = detect_onset_after(
                energy_db=energy_db,
                sample_rate=sample_rate,
                frame_length=frame_length,
                start_ms=start_ms,
                threshold_db=dynamic_threshold,
                min_frames=min_frames,
            )

        result["max_energy_db"] = float(np.max(energy_db)) if energy_db.size else float("-inf")
        result["median_energy_db"] = float(np.median(energy_db)) if energy_db.size else float("-inf")
        result["dynamic_threshold_db"] = dynamic_threshold
        result["fallback_used"] = fallback_used

        if onset_ms is None:
            result["status"] = "no_speech_detected"
            result["note"] = "No onset above threshold after playback end"
        else:
            result["onset_ms_from_recording_start"] = onset_ms
            result["latency_ms_from_playback_end"] = onset_ms - playback_end_rel
            result["note"] = ""

        if save_plots_dir:
            try:
                import matplotlib.pyplot as plt

                t = np.arange(len(signal)) / sample_rate * 1000.0
                fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
                axes[0].plot(t, signal, color="steelblue", lw=0.8)
                axes[0].axvline(playback_end_rel, color="orange", ls="--", lw=1, label="playback_end_rel")
                axes[0].axvline(start_ms, color="red", ls="--", lw=1, label="start_ms (guarded)")
                if onset_ms is not None:
                    axes[0].axvline(onset_ms, color="lime", ls="--", lw=1.2, label="detected_onset")
                axes[0].set_ylabel("Amplitude")
                axes[0].legend(loc="upper right")

                energy_t = (np.arange(len(energy_db)) + frame_length / 2.0) / sample_rate * 1000.0
                axes[1].plot(energy_t, energy_db, color="gray", lw=0.8, label="Energy (dB)")
                axes[1].axhline(dynamic_threshold, color="purple", ls="--", lw=1, label="threshold")
                axes[1].axvline(start_ms, color="red", ls="--", lw=1)
                axes[1].set_ylabel("Energy (dB)")
                axes[1].set_xlabel("Time (ms from recording start)")
                axes[1].legend(loc="upper right")

                fname = f"{row.get('participant_id','pid')}_trial{row.get('trial','')}_{row.get('voice','')}_{strip_accents(str(row.get('word','')))}.png"
                plt.tight_layout()
                fig.savefig(os.path.join(save_plots_dir, fname), dpi=150)
                plt.close(fig)
            except Exception as plot_err:
                # QC保存失敗は致命的でないので警告だけ
                print(f"⚠️ Plot save failed for {wav_path}: {plot_err}")

        records.append(result)

    out_df = pd.DataFrame(records)
    print("解析完了")
    print(f"  総試行数        : {len(out_df)}")
    print(f"  潜時検出成功    : {out_df['latency_ms_from_playback_end'].notna().sum()}")
    print(f"  ファイル欠損    : {(out_df['status'] == 'missing').sum()}")
    print(f"  検出失敗        : {(out_df['status'] == 'no_speech_detected').sum()}")
    return out_df


def main() -> None:
    args = parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Resolve root relative to CWD first, then fallback to script directory
    root_candidate = os.path.abspath(args.root)
    if not os.path.isdir(root_candidate):
        alt = os.path.abspath(os.path.join(script_dir, args.root))
        if os.path.isdir(alt):
            root_candidate = alt
        else:
            raise FileNotFoundError(f"root ディレクトリが見つかりません: {args.root} (tried {root_candidate} and {alt})")

    root = root_candidate
    csv_path = find_results_csv(root, args.csv)
    print(f"Root      : {root}")
    print(f"CSV       : {csv_path}")

    results = analyze(
        root=root,
        csv_path=csv_path,
        threshold_db=args.threshold_db,
        frame_ms=args.frame_ms,
        min_frames=args.min_frames,
        guard_ms=args.guard_ms,
        save_plots=args.save_plots,
    )

    out_path = os.path.abspath(args.output) if args.output else os.path.join(root, "latency_summary.csv")
    results.to_csv(out_path, index=False, float_format="%.3f")
    print(f"保存しました: {out_path}")


if __name__ == "__main__":
    main()
