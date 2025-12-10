#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
L2 -> L1 Translation Production Task
スペイン語の単語を提示し、日本語で応答する課題。
"""

import os
import random
import pandas as pd
import time
from datetime import datetime
import pygame
from pygame.locals import FULLSCREEN, QUIT, KEYDOWN, K_ESCAPE, K_SPACE, K_5
import logging as std_logging
import sounddevice as sd
import soundfile as sf
import argparse
import gc

# --- 実験パラメータ ---
FIXED_STIMULUS_TIME = 6.0    # 単語提示時間（録音時間と同じ）
ITI_DURATION = 1.5          # 試行間間隔（秒）
DEBUG = False               # デバッグモード
DEFAULT_FULLSCREEN_MODE = True  # フルスクリーンモードのデフォルト

# --- オーディオ録音設定 ---
AUDIO_SAMPLE_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_DTYPE = 'float32'

# --- ディレクトリ設定 ---
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:  # Interactive mode
    SCRIPT_DIR = os.getcwd()

OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'L2_to_L1_Recording')
DATA_DIR = os.path.join(OUTPUT_DIR, 'data')
REC_DIR = os.path.join(OUTPUT_DIR, 'recordings')
STIM_AUDIO_DIR = os.path.join(SCRIPT_DIR, 'real_stimuli_audio')
SOUND_ICON_PATH = os.path.join(SCRIPT_DIR, 'sound.png')
FONT_PATH = os.path.join(SCRIPT_DIR, 'fonts', 'static', 'NotoSansJP-Regular.ttf')

for directory in [OUTPUT_DIR, DATA_DIR, REC_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# --- ロギング設定 ---
def setup_logging(participant_id, session_label=None):
    """詳細なロギング設定"""
    log_suffix = f"_{session_label}" if session_label else ""
    log_filename = f"{participant_id}_l2_to_l1{log_suffix}.log"
    log_filepath = os.path.join(DATA_DIR, log_filename)
    logger = std_logging.getLogger()
    logger.setLevel(std_logging.INFO)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    log_formatter = std_logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)s\t%(message)s',
                                         datefmt='%Y-%m-%d %H:%M:%S')
    file_handler = std_logging.FileHandler(log_filepath, encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    console_handler = std_logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)
    return log_filepath

# --- ロギング用関数 ---
def log_message(message):
    """メッセージのログ出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    std_logging.info(message)

# --- コマンドライン引数パーサー ---
def parse_arguments():
    """コマンドライン引数の解析"""
    parser = argparse.ArgumentParser(description='L2 -> L1 Translation Production Task')
    parser.add_argument('--id', '-i', dest='participant_id', type=str, help='参加者ID（例: 001）')
    parser.add_argument('--fullscreen', '-f', dest='fullscreen', action='store_true', help='フルスクリーンモードで実行')
    parser.add_argument('--force-create', dest='force_create', action='store_true', help='参加者情報を強制的に作成')
    args = parser.parse_args()
    return args

# --- テキストベースのユーザー情報入力 ---
def get_participant_info_text():
    """テキストベースのインターフェースで参加者情報を取得"""
    print("\n=== L2 -> L1 Translation Task ===\n")
    exp_info = {
        'participant_id': None,
        'fullscreen': DEFAULT_FULLSCREEN_MODE,
        'date': datetime.now().strftime("%Y_%b_%d_%H%M"),
        'datetime_str': datetime.now().strftime("%Y%m%d_%H%M%S")
    }
    exp_info['participant_id'] = input("参加者ID: ")
    # 常にフルスクリーンモードに設定
    exp_info['fullscreen'] = True
    info_file = os.path.join(DATA_DIR, f"{exp_info['participant_id']}_info.csv")
    exp_info['force_create'] = not os.path.exists(info_file)
    return exp_info

# --- 参加者情報の作成 ---
def create_participant_info(participant_id):
    """参加者情報を新規作成"""
    info_data = {
        'participant_id': [participant_id],
        'date': [datetime.now().strftime("%Y-%m-%d_%H-%M-%S")]
    }
    info_file = os.path.join(DATA_DIR, f"{participant_id}_info.csv")
    pd.DataFrame(info_data).to_csv(info_file, index=False)
    log_message(f"参加者情報を新規作成しました: {participant_id}")
    return info_data

# --- テキスト表示関数 ---
def display_text(screen, text, y_offset=0, font_size=36, color=(255, 255, 255)):
    """テキストを画面中央に表示"""
    try:
        font_file = FONT_PATH
        font = None
        if os.path.exists(font_file):
            try:
                font = pygame.font.Font(font_file, font_size)
            except pygame.error as e:
                log_message(f"指定フォント読み込みエラー ({font_file}): {e}. 代替フォントを探します。")
                font = None

        if font is None:
            fonts_dir = os.path.join(SCRIPT_DIR, 'fonts', 'static')
            if os.path.exists(fonts_dir):
                noto_fonts = [f for f in os.listdir(fonts_dir) if f.startswith('NotoSansJP-') and f.endswith('.ttf')]
                if noto_fonts:
                    alt_font_path = os.path.join(fonts_dir, noto_fonts[0])
                    try:
                        font = pygame.font.Font(alt_font_path, font_size)
                        log_message(f"代替フォントを使用: {noto_fonts[0]}")
                    except pygame.error as e:
                        log_message(f"代替フォント読み込みエラー ({alt_font_path}): {e}. システムフォントを使用します。")
                        font = pygame.font.SysFont(None, font_size)
                else:
                    log_message("fonts/static に NotoSansJP フォントが見つかりません。システムフォントを使用します。")
                    font = pygame.font.SysFont(None, font_size)
            else:
                log_message("フォントディレクトリが見つかりません。システムフォントを使用します。")
                font = pygame.font.SysFont(None, font_size)

        lines = text.split('\n')
        screen_width, screen_height = screen.get_size()
        rendered_lines = [font.render(line, True, color) for line in lines]
        total_height = sum(surface.get_rect().height for surface in rendered_lines)
        start_y = (screen_height - total_height) // 2 + y_offset
        current_y = start_y
        for text_surface in rendered_lines:
            text_rect = text_surface.get_rect(center=(screen_width // 2, current_y + text_surface.get_rect().height // 2))
            screen.blit(text_surface, text_rect)
            current_y += text_surface.get_rect().height
        pygame.display.flip()
    except Exception as e:
        log_message(f"テキスト表示エラー: {e}")
        import traceback
        log_message(traceback.format_exc())

# --- 刺激準備関数 ---
def get_all_stimuli():
    """スペイン語提示・日本語応答用の刺激を取得"""
    stimuli = [
        {'spanish': 'elote', 'japanese': 'とうもろこし'},
        {'spanish': 'ardilla', 'japanese': 'リス'},
        {'spanish': 'basurero', 'japanese': 'ごみ箱'},
        {'spanish': 'caballo', 'japanese': '馬'},
        {'spanish': 'cebolla', 'japanese': '玉ねぎ'},
        {'spanish': 'cinta', 'japanese': 'テープ'},
        {'spanish': 'conejo', 'japanese': 'ウサギ'},
        {'spanish': 'cuaderno', 'japanese': 'ノート'},
        {'spanish': 'fresas', 'japanese': 'いちご'},
        {'spanish': 'gato', 'japanese': '猫'},
        {'spanish': 'grapadora', 'japanese': 'ホッチキス'},
        {'spanish': 'hongos', 'japanese': 'きのこ'},
        {'spanish': 'lapiz', 'japanese': '鉛筆'},
        {'spanish': 'lechuga', 'japanese': 'レタス'},
        {'spanish': 'loro', 'japanese': 'オウム'},
        {'spanish': 'manzana', 'japanese': 'りんご'},
        {'spanish': 'naranja', 'japanese': 'オレンジ'},
        {'spanish': 'oso', 'japanese': '熊'},
        {'spanish': 'pato', 'japanese': 'アヒル'},
        {'spanish': 'pez', 'japanese': '魚'},
        {'spanish': 'reloj', 'japanese': '時計'},
        {'spanish': 'sandia', 'japanese': 'スイカ'},
        {'spanish': 'tijeras', 'japanese': 'ハサミ'},
        {'spanish': 'tiza', 'japanese': 'チョーク'},
    ]
    for idx, entry in enumerate(stimuli, start=1):
        entry['word_id'] = idx
    random.shuffle(stimuli)
    return stimuli

# --- 十字の表示 ---
def show_fixation(screen, duration):
    """十字固視点を表示"""
    screen.fill((0, 0, 0))
    screen_width, screen_height = screen.get_size()
    center_x, center_y = screen_width // 2, screen_height // 2
    fix_len = 25
    fix_width = 4
    pygame.draw.line(screen, (255, 255, 255), (center_x - fix_len, center_y), (center_x + fix_len, center_y), fix_width)
    pygame.draw.line(screen, (255, 255, 255), (center_x, center_y - fix_len), (center_x, center_y + fix_len), fix_width)
    pygame.display.flip()
    start_wait = time.time()
    while time.time() - start_wait < duration:
        for event in pygame.event.get():
            if event.type == QUIT:
                return False
            elif event.type == KEYDOWN and event.key == K_ESCAPE:
                return False
        pygame.time.wait(10)
    return True

# --- fMRIトリガー待機関数 ---
def wait_for_trigger(screen):
    """fMRIスキャナーのトリガー（キー'5'）を待機"""
    screen.fill((0, 0, 0))
    display_text(screen, "準備ができたらキーボードの 5 を押してください")
    waiting = True
    trigger_time = None
    while waiting:
        for event in pygame.event.get():
            if event.type == QUIT:
                return False, None
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    return False, None
                elif event.key == K_5:
                    trigger_time = time.time()
                    waiting = False
                    screen.fill((0, 0, 0))
                    pygame.display.flip()
    log_message(f"トリガー受信: 絶対時間 {trigger_time:.4f}")
    return True, trigger_time

class L2ToL1Task:
    def __init__(self):
        pygame.init()
        self.participant_data = {}
        self.session_label = None
        self.log_file = None
        self.csv_filename = None
        self.timestamps_filename = None
        self.recordings_dir = None
        self.audio_available = False
        self.audio_error = None
        self.fullscreen = False
        self.screen = None
        self.clock = None
        self.trigger_time = None
        self.detailed_log = []
        self.timestamps = []
        self.sound_image = None
        self.playback_available = False
        self.playback_error = None

    def setup_screen(self, fullscreen=False):
        """画面の初期化"""
        self.fullscreen = fullscreen
        try:
            if fullscreen:
                display_info = pygame.display.Info()
                self.screen = pygame.display.set_mode(
                    (display_info.current_w, display_info.current_h),
                    FULLSCREEN | pygame.DOUBLEBUF
                )
                pygame.mouse.set_visible(False)
            else:
                self.screen = pygame.display.set_mode((1024, 768), pygame.DOUBLEBUF)
        except pygame.error as e:
            log_message(f"画面設定エラー: {e}. ウィンドウモード(1024x768)を使用します。")
            self.screen = pygame.display.set_mode((1024, 768), pygame.DOUBLEBUF)
            self.fullscreen = False
        pygame.display.set_caption('L2 -> L1 Translation Task')
        self.clock = pygame.time.Clock()
        pygame.mouse.set_visible(False)
        self.prepare_sound_image()
        return self.screen

    def prepare_sound_image(self):
        """音声提示中に表示するアイコンを準備"""
        if self.screen is None:
            self.sound_image = None
            return
        if not os.path.exists(SOUND_ICON_PATH):
            log_message(f"警告: 音声アイコンファイルが見つかりません ({SOUND_ICON_PATH})")
            self.sound_image = None
            return
        try:
            image = pygame.image.load(SOUND_ICON_PATH).convert_alpha()
            screen_width, screen_height = self.screen.get_size()
            target_size = int(min(screen_width, screen_height) * 0.5)
            orig_width, orig_height = image.get_width(), image.get_height()
            scale = min(target_size / orig_width, target_size / orig_height)
            new_width, new_height = int(orig_width * scale), int(orig_height * scale)
            if new_width <= 0 or new_height <= 0:
                self.sound_image = image
            else:
                self.sound_image = pygame.transform.smoothscale(image, (new_width, new_height))
        except pygame.error as e:
            log_message(f"音声アイコン読み込みエラー: {e}")
            self.sound_image = None

    def show_audio_prompt(self):
        """音声再生中のビジュアル表示"""
        if self.screen is None:
            return
        self.screen.fill((0, 0, 0))
        if self.sound_image:
            image_rect = self.sound_image.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2))
            self.screen.blit(self.sound_image, image_rect)
        else:
            display_text(self.screen, "音声を聴いてください", font_size=64)
            return
        pygame.display.flip()

    def get_participant_info(self, args=None):
        """参加者情報の取得"""
        if args and args.participant_id:
            exp_info = {'participant_id': args.participant_id,
                        'fullscreen': args.fullscreen, 'force_create': args.force_create}
        else:
            exp_info = get_participant_info_text()
        exp_info['fullscreen'] = True

        participant_id = exp_info['participant_id']
        info_file = os.path.join(DATA_DIR, f"{participant_id}_info.csv")

        if not os.path.exists(info_file) or exp_info.get('force_create', False):
            create_participant_info(participant_id)
        else:
            participant_info = pd.read_csv(info_file).iloc[0].to_dict()
            log_message(f"参加者情報を読み込みました: {participant_id}")

        session_label = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_label = session_label
        self.participant_data = {'participant_id': participant_id, 'date': session_label}

        base_filename = f"{participant_id}_l2_to_l1_{session_label}"
        self.csv_filename = os.path.join(DATA_DIR, f"{base_filename}.csv")
        self.timestamps_filename = os.path.join(DATA_DIR, f"{base_filename}_timestamps.csv")
        self.recordings_dir = os.path.join(REC_DIR, participant_id, session_label)
        os.makedirs(self.recordings_dir, exist_ok=True)

        self.log_file = setup_logging(participant_id, session_label)
        log_message(f"参加者: {participant_id}, セッション: {session_label}")
        log_message(f"録音保存ディレクトリ: {self.recordings_dir}")
        log_message(f"タイムスタンプファイル: {self.timestamps_filename}")
        log_message(f"試行データファイル: {self.csv_filename}")

        return exp_info.get('fullscreen', DEFAULT_FULLSCREEN_MODE)

    def show_instructions(self):
        """実験の教示表示"""
        self.screen.fill((0, 0, 0))
        instruction_text = (
            "これから翻訳産出課題を行います。\n\n"
            "スペイン語の音声が再生されますので、\n"
            "できるだけ早く、正確な日本語で声に出して答えてください。\n\n"
            "音声再生中は画面にアイコンが表示され、その間に約6秒間録音されます。\n"
            "思い出せない場合は「わかりません」と答えてください。"
        )
        display_text(self.screen, instruction_text)
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == QUIT:
                    return False
                elif event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        return False
                    elif event.key == K_SPACE:
                        waiting = False
        return True

    def initialize_audio(self):
        """音声録音デバイスの初期化"""
        try:
            sd.query_devices()
            self.audio_available = True
            self.audio_error = None
            log_message("音声録音デバイスを認識しました (sounddevice)。")
        except Exception as e:
            self.audio_available = False
            self.audio_error = str(e)
            log_message(f"警告: 音声録音を利用できません: {e}")

    def initialize_playback(self):
        """音声提示用のデバイス初期化"""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=AUDIO_SAMPLE_RATE)
            self.playback_available = True
            self.playback_error = None
            log_message("音声再生デバイスを初期化しました (pygame.mixer)。")
        except pygame.error as e:
            self.playback_available = False
            self.playback_error = str(e)
            log_message(f"警告: 音声再生を利用できません: {e}")

    def get_trial_audio_path(self, trial_idx, trial):
        """試行ごとの録音ファイルパスを生成"""
        word = trial.get('spanish', f"trial{trial_idx+1}")
        safe_word = ''.join(ch for ch in word if ch.isalnum()) or f"trial{trial_idx+1}"
        filename = f"{self.participant_data['participant_id']}_{self.session_label}_trial{trial_idx+1:02d}_{safe_word}.wav"
        return os.path.join(self.recordings_dir, filename)

    def run_trial(self, trial_idx, trial):
        """1試行の実行"""
        log_message(f"試行 {trial_idx+1} 開始: スペイン語 '{trial['spanish']}'")
        gc.collect()

        audio_path = None
        audio_filename = None
        recording = None
        audio_start_time = None
        audio_start_relative_time = None
        audio_end_relative_time = None
        audio_end_time = None
        playback_sound = None
        playback_channel = None
        playback_file = None
        playback_duration = None
        playback_start_time = None
        playback_end_time = None
        playback_start_relative_time = None
        playback_end_relative_time = None

        trial_abs_start_time = time.time()
        trial_relative_start_time = trial_abs_start_time - self.trigger_time if self.trigger_time else 0

        trial_log_entry = {
            'event_type': 'trial_start',
            'trial': trial_idx + 1,
            'onset': trial_relative_start_time,
            'duration': None,
            'spanish_word': trial['spanish'],
            'japanese_target': trial['japanese'],
            'timestamp': datetime.fromtimestamp(trial_abs_start_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        self.detailed_log.append(trial_log_entry)

        self.show_audio_prompt()

        stim_audio_path = os.path.join(STIM_AUDIO_DIR, f"{trial['spanish']}.mp3")
        if self.playback_available and os.path.exists(stim_audio_path):
            try:
                playback_sound = pygame.mixer.Sound(stim_audio_path)
                playback_file = os.path.basename(stim_audio_path)
                playback_duration = playback_sound.get_length()
            except pygame.error as e:
                playback_sound = None
                playback_file = None
                playback_duration = None
                log_message(f"音声再生データ読み込みエラー ({stim_audio_path}): {e}")
        else:
            if not os.path.exists(stim_audio_path):
                log_message(f"警告: 音声ファイルが見つかりません: {stim_audio_path}")
            elif not self.playback_available:
                log_message("音声再生機能が利用できないため、音声提示をスキップします。")

        if self.audio_available:
            audio_path = self.get_trial_audio_path(trial_idx, trial)
            audio_filename = os.path.basename(audio_path)
            try:
                recording = sd.rec(
                    int(FIXED_STIMULUS_TIME * AUDIO_SAMPLE_RATE),
                    samplerate=AUDIO_SAMPLE_RATE,
                    channels=AUDIO_CHANNELS,
                    dtype=AUDIO_DTYPE
                )
                audio_start_time = time.time()
                audio_start_relative_time = audio_start_time - self.trigger_time if self.trigger_time else 0
                self.detailed_log.append({
                    'event_type': 'audio_recording_start',
                    'trial': trial_idx + 1,
                    'onset': audio_start_relative_time,
                    'duration': FIXED_STIMULUS_TIME,
                    'audio_file': audio_filename,
                    'timestamp': datetime.fromtimestamp(audio_start_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                })
                log_message(f"試行 {trial_idx+1}: 音声録音開始 ({audio_filename})")
            except Exception as e:
                self.audio_available = False
                self.audio_error = str(e)
                recording = None
                audio_path = None
                audio_filename = None
                log_message(f"音声録音開始エラー: {e}. この後の試行では録音をスキップします。")

        if playback_sound is not None:
            try:
                pygame.mixer.stop()
                playback_channel = playback_sound.play()
                if playback_channel is not None:
                    playback_start_time = time.time()
                    playback_start_relative_time = playback_start_time - self.trigger_time if self.trigger_time else 0
                    self.detailed_log.append({
                        'event_type': 'audio_playback_start',
                        'trial': trial_idx + 1,
                        'onset': playback_start_relative_time,
                        'duration': playback_duration,
                        'playback_file': playback_file,
                        'timestamp': datetime.fromtimestamp(playback_start_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    })
                    log_message(f"試行 {trial_idx+1}: 音声再生開始 ({playback_file})")
                else:
                    log_message(f"音声再生チャンネルを取得できませんでした ({stim_audio_path})")
            except pygame.error as e:
                playback_channel = None
                playback_sound = None
                log_message(f"音声再生開始エラー ({stim_audio_path}): {e}")

        prompt_onset_time = time.time()
        prompt_log_entry = {
            'event_type': 'prompt_onset',
            'trial': trial_idx + 1,
            'onset': prompt_onset_time - self.trigger_time if self.trigger_time else 0,
            'duration': FIXED_STIMULUS_TIME,
            'spanish_word': trial['spanish'],
            'display': 'sound_icon',
            'playback_file': playback_file,
            'timestamp': datetime.fromtimestamp(prompt_onset_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        self.detailed_log.append(prompt_log_entry)

        stimulus_start_time = time.time()
        playback_end_logged = False
        while time.time() - stimulus_start_time < FIXED_STIMULUS_TIME:
            for event in pygame.event.get():
                if event.type == QUIT:
                    if recording is not None:
                        try:
                            sd.stop()
                        except Exception:
                            pass
                    return None, trial_abs_start_time, time.time()
                elif event.type == KEYDOWN and event.key == K_ESCAPE:
                    log_message("ESCキーにより中断します。")
                    if recording is not None:
                        try:
                            sd.stop()
                        except Exception:
                            pass
                    return None, trial_abs_start_time, time.time()
            if playback_channel and not playback_end_logged and not playback_channel.get_busy():
                playback_end_time = time.time()
                playback_end_relative_time = playback_end_time - self.trigger_time if self.trigger_time else 0
                self.detailed_log.append({
                    'event_type': 'audio_playback_end',
                    'trial': trial_idx + 1,
                    'onset': playback_end_relative_time,
                    'duration': 0.0,
                    'playback_file': playback_file,
                    'timestamp': datetime.fromtimestamp(playback_end_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                })
                playback_end_logged = True
            pygame.time.wait(10)

        stimulus_end_time = time.time()

        if recording is not None and audio_path:
            try:
                sd.wait()
                sf.write(audio_path, recording, AUDIO_SAMPLE_RATE)
                audio_end_time = time.time()
                audio_end_relative_time = audio_end_time - self.trigger_time if self.trigger_time else 0
                self.detailed_log.append({
                    'event_type': 'audio_recording_end',
                    'trial': trial_idx + 1,
                    'onset': audio_end_relative_time,
                    'duration': 0.0,
                    'audio_file': audio_filename,
                    'timestamp': datetime.fromtimestamp(audio_end_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                })
                log_message(f"試行 {trial_idx+1}: 音声録音保存 ({audio_filename})")
            except Exception as e:
                log_message(f"音声保存エラー: {e}")
                audio_filename = None
                audio_path = None

        if playback_channel and playback_channel.get_busy():
            playback_channel.stop()
        if playback_start_time and playback_end_time is None:
            playback_end_time = time.time()
            playback_end_relative_time = playback_end_time - self.trigger_time if self.trigger_time else 0
            self.detailed_log.append({
                'event_type': 'audio_playback_end',
                'trial': trial_idx + 1,
                'onset': playback_end_relative_time,
                'duration': 0.0,
                'playback_file': playback_file,
                'timestamp': datetime.fromtimestamp(playback_end_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            })
            playback_end_logged = True

        fixation_start_time = time.time()
        fixation_log_entry = {
            'event_type': 'fixation_onset',
            'trial': trial_idx + 1,
            'onset': fixation_start_time - self.trigger_time if self.trigger_time else 0,
            'duration': ITI_DURATION,
            'timestamp': datetime.fromtimestamp(fixation_start_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        self.detailed_log.append(fixation_log_entry)

        if not show_fixation(self.screen, ITI_DURATION):
            log_message("固視点表示中に中断されました。")
            return None, trial_abs_start_time, time.time()
        log_message(f"ITI: {ITI_DURATION:.2f}秒 適用完了")

        trial_abs_end_time = time.time()
        trial_relative_end_time = trial_abs_end_time - self.trigger_time if self.trigger_time else 0
        trial_duration = trial_abs_end_time - trial_abs_start_time

        trial_log_entry['duration'] = trial_duration
        trial_end_log_entry = {
            'event_type': 'trial_end',
            'trial': trial_idx + 1,
            'onset': trial_relative_end_time,
            'duration': 0.0,
            'spanish_word': trial['spanish'],
            'timestamp': datetime.fromtimestamp(trial_abs_end_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        self.detailed_log.append(trial_end_log_entry)

        self.timestamps.append({
            'participant_id': self.participant_data['participant_id'],
            'trial': trial_idx + 1,
            'spanish_word': trial['spanish'],
            'japanese_target': trial['japanese'],
            'word_id': trial['word_id'],
            'trial_abs_start_time': trial_abs_start_time,
            'trial_abs_end_time': trial_abs_end_time,
            'trial_relative_start_time': trial_relative_start_time,
            'trial_relative_end_time': trial_relative_end_time,
            'trial_duration': trial_duration,
            'prompt_onset_relative_time': prompt_onset_time - self.trigger_time if self.trigger_time else 0,
            'stimulus_duration': FIXED_STIMULUS_TIME,
            'iti_duration': ITI_DURATION,
            'trigger_time': self.trigger_time,
            'audio_file': audio_filename,
            'audio_onset_abs_time': audio_start_time,
            'audio_onset_relative_time': audio_start_relative_time,
            'audio_offset_abs_time': audio_end_time,
            'audio_offset_relative_time': audio_end_relative_time,
            'playback_audio_file': playback_file,
            'playback_duration': playback_duration,
            'audio_playback_start_abs_time': playback_start_time,
            'audio_playback_start_relative_time': playback_start_relative_time,
            'audio_playback_end_abs_time': playback_end_time,
            'audio_playback_end_relative_time': playback_end_relative_time
        })

        trial_info = {
            'participant_id': self.participant_data['participant_id'],
            'trial': trial_idx + 1,
            'spanish_word': trial['spanish'],
            'japanese_target': trial['japanese'],
            'word_id': trial['word_id'],
            'recording_file': audio_filename,
            'trial_start_time_abs': trial_abs_start_time,
            'trial_end_time_abs': trial_abs_end_time,
            'trial_duration': trial_duration,
            'iti_duration': ITI_DURATION,
            'playback_audio_file': playback_file,
            'playback_duration': playback_duration,
            'date': self.participant_data['date'],
            'trigger_time': self.trigger_time
        }

        log_message(f"試行 {trial_idx+1} 完了, スペイン語: {trial['spanish']}, 試行時間: {trial_duration:.3f}秒")

        return trial_info, trial_abs_start_time, trial_abs_end_time

    def save_detailed_log(self, interrupted=False):
        """詳細なイベントログをCSVに保存"""
        if not self.detailed_log:
            log_message("保存する詳細ログデータがありません。")
            return None
        try:
            log_df = pd.DataFrame(self.detailed_log)
            log_df['participant_id'] = self.participant_data['participant_id']
            log_df['interrupted'] = interrupted
            log_df['recording_directory'] = self.recordings_dir
            log_df = log_df.sort_values(by='onset').reset_index(drop=True)
            detailed_log_filename = os.path.join(
                DATA_DIR,
                f"{self.participant_data['participant_id']}_{self.session_label}_detailed_log.csv"
            )
            log_df.to_csv(detailed_log_filename, index=False, float_format='%.6f')
            log_message(f"詳細ログを保存しました: {detailed_log_filename}")
            return detailed_log_filename
        except Exception as e:
            log_message(f"詳細ログの保存に失敗しました: {e}")
            import traceback
            log_message(traceback.format_exc())
            return None

    def save_timestamps(self):
        """タイムスタンプデータをCSVに保存"""
        if not self.timestamps:
            log_message("保存するタイムスタンプデータがありません。")
            return False
        try:
            ts_df = pd.DataFrame(self.timestamps)
            time_cols = ['trial_abs_start_time', 'trial_abs_end_time', 'trigger_time']
            for col in time_cols:
                if col in ts_df.columns:
                    ts_df[f'{col}_str'] = pd.to_datetime(ts_df[col], unit='s').dt.strftime('%Y-%m-%d %H:%M:%S.%f')

            ts_df.to_csv(self.timestamps_filename, index=False, float_format='%.6f')
            log_message(f"タイムスタンプデータを保存しました: {self.timestamps_filename}")
            return True
        except Exception as e:
            log_message(f"タイムスタンプデータの保存に失敗しました: {e}")
            import traceback
            log_message(traceback.format_exc())
            return False

    def run_task(self):
        """翻訳産出課題の実行"""
        trials = get_all_stimuli()
        if not trials:
            log_message("エラー: 有効な刺激がありません。")
            return False
        log_message(f"刺激数: {len(trials)}")

        self.initialize_audio()
        if not self.audio_available:
            log_message("音声録音機能なしで実験を実行します。")
            if self.audio_error:
                log_message(f"録音初期化エラー: {self.audio_error}")

        self.initialize_playback()
        if not self.playback_available:
            log_message("警告: 音声再生機能なしで実験を実行します。")
            if self.playback_error:
                log_message(f"再生初期化エラー: {self.playback_error}")

        if not self.show_instructions():
            log_message("教示画面で中断されました。")
            return False

        self.screen.fill((0, 0, 0))
        display_text(self.screen, "スキャナーのトリガー信号 (5) を待っています...")
        trigger_success, self.trigger_time = wait_for_trigger(self.screen)
        if not trigger_success:
            log_message("トリガー待機中に中断されました。")
            return False

        exp_start_abs_time = time.time()
        experiment_start_log = {
            'event_type': 'experiment_start',
            'trial': 0,
            'onset': exp_start_abs_time - self.trigger_time,
            'duration': 0.0,
            'timestamp': datetime.fromtimestamp(exp_start_abs_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        self.detailed_log.append(experiment_start_log)

        initial_rest_start_time = time.time()
        initial_fixation_log = {
            'event_type': 'initial_long_rest',
            'trial': 0,
            'onset': initial_rest_start_time - self.trigger_time,
            'duration': 10.0,
            'timestamp': datetime.fromtimestamp(initial_rest_start_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        self.detailed_log.append(initial_fixation_log)
        if not show_fixation(self.screen, 10.0):
            log_message("初期long rest中に中断されました。")
            self.save_timestamps()
            self.save_detailed_log(interrupted=True)
            return False

        trial_data = []
        interrupted = False
        last_trial_idx = -1

        try:
            for trial_idx, trial in enumerate(trials):
                last_trial_idx = trial_idx
                result, _, _ = self.run_trial(trial_idx, trial)

                if result is None:
                    interrupted = True
                    log_message(f"試行 {trial_idx+1} で中断されました。")
                    break

                trial_data.append(result)

                if trial_idx % 5 == 0:
                    try:
                        import psutil
                        process = psutil.Process(os.getpid())
                        mem_info = process.memory_info()
                        log_message(f"試行 {trial_idx+1} 終了後メモリ使用量: {mem_info.rss / 1024 / 1024:.1f} MB")
                    except ImportError:
                        pass
                    except Exception as e:
                        log_message(f"メモリ使用量取得エラー: {e}")
                    gc.collect()

        except Exception as e:
            log_message(f"実験ループ中に予期せぬエラーが発生しました (試行 {last_trial_idx + 1}): {e}")
            import traceback
            log_message(traceback.format_exc())
            interrupted = True

        exp_end_abs_time = time.time()
        experiment_end_log = {
            'event_type': 'experiment_end',
            'trial': last_trial_idx + 1,
            'onset': exp_end_abs_time - self.trigger_time,
            'duration': 0.0,
            'timestamp': datetime.fromtimestamp(exp_end_abs_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            'interrupted': interrupted,
            'completed_trials': len(trial_data)
        }
        self.detailed_log.append(experiment_end_log)

        final_rest_start_time = time.time()
        final_fixation_log = {
            'event_type': 'final_long_rest',
            'trial': last_trial_idx + 1,
            'onset': final_rest_start_time - self.trigger_time,
            'duration': 10.0,
            'timestamp': datetime.fromtimestamp(final_rest_start_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }
        self.detailed_log.append(final_fixation_log)

        if not show_fixation(self.screen, 10.0):
            log_message("最終long rest中に中断されました。")

        self.save_timestamps()

        if trial_data:
            try:
                df = pd.DataFrame(trial_data)
                df.to_csv(self.csv_filename, index=False, float_format='%.6f')
                log_message(f"試行データをCSVに保存しました: {self.csv_filename}")
            except Exception as e:
                log_message(f"試行データCSV保存エラー: {e}")
        else:
            log_message("保存する試行データがありません。")

        self.save_detailed_log(interrupted)

        self.screen.fill((0, 0, 0))
        end_text = "翻訳課題が終了しました。\n\nお疲れ様でした。"
        if interrupted:
            end_text = (
                f"翻訳課題が中断されました。\n\n"
                f"完了した試行: {len(trial_data)}/{len(trials)}\n\nお疲れ様でした。"
            )
        display_text(self.screen, end_text)
        pygame.time.wait(3000)

        return not interrupted

    def cleanup(self):
        """リソース解放"""
        log_message("クリーンアップ処理中...")
        pygame.quit()
        log_message("Pygameリソース解放完了")
        log_message("実験プログラム終了")

    def run(self, args=None):
        """実験全体の実行"""
        try:
            fullscreen = self.get_participant_info(args)
            self.setup_screen(fullscreen)
            task_result = self.run_task()
            return task_result
        except KeyboardInterrupt:
            log_message("キーボード割り込みにより終了します。")
            self.save_timestamps()
            self.save_detailed_log(interrupted=True)
            return False
        except Exception as e:
            log_message(f"実験実行中に予期せぬエラーが発生しました: {e}")
            import traceback
            log_message(traceback.format_exc())
            self.save_timestamps()
            self.save_detailed_log(interrupted=True)
            return False
        finally:
            self.cleanup()


if __name__ == "__main__":
    try:
        args = parse_arguments()
        task = L2ToL1Task()
        result = task.run(args)

        if result:
            print("\n翻訳課題は正常に完了しました。")
        else:
            print("\n課題は中断されたか、エラーが発生しました。ログファイルを確認してください。")

    except SystemExit:
        print("プログラムが終了しました。")
    except Exception as e:
        print(f"\n予期せぬ致命的エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
