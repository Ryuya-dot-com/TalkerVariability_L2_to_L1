(() => {
  // Constants
  const WORDS = [
    'ardilla','basurero','caballo','cebolla','cinta','conejo',
    'cuaderno','elote','fresas','gato','grapadora','hongos',
    'lapiz','lechuga','loro','manzana','naranja','oso',
    'pato','pez','reloj','sandia','tijeras','tiza',
  ];
  const STIM_PATH = 'real_stimuli_audio';
  const RECORD_DURATION_MS = 6000; // 6 seconds
  const ITI_MS = 1500; // 1.5 seconds

  // DOM
  const preloadBtn = document.getElementById('preload-btn');
  const startBtn = document.getElementById('start-btn');
  const downloadBtn = document.getElementById('download-btn');
  const statusEl = document.getElementById('status');
  const logEl = document.getElementById('log');
  const fixationEl = document.getElementById('fixation');
  const messageEl = document.getElementById('message');
  const soundIconEl = document.getElementById('sound-icon');
  const participantInput = document.getElementById('participant-id');

  // Helpers
  const setStatus = (txt) => statusEl.textContent = txt;
  const setLog = (txt) => logEl.textContent = txt;
  const delay = (ms) => new Promise(res => setTimeout(res, ms));

  function mulberry32(seed) {
    return function() {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function seededShuffle(arr, rng) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }
  const parseNumericId = (pid) => {
    const digits = pid.match(/\d+/g);
    return digits ? parseInt(digits.join(''), 10) : 0;
  };

  // Build alternating, seeded order
  function buildOrder(participantId) {
    const n = parseNumericId(participantId);
    const rng = mulberry32(n * 1000 + 7);
    const firstHalf = seededShuffle(WORDS.slice(0, 12), rng);
    const secondHalf = seededShuffle(WORDS.slice(12), rng);
    let takeFirst = rng() < 0.5; // deterministic by seed
    const order = [];
    let i = 0, j = 0;
    while (i < firstHalf.length || j < secondHalf.length) {
      if (takeFirst && i < firstHalf.length) {
        order.push(firstHalf[i++]);
      } else if (!takeFirst && j < secondHalf.length) {
        order.push(secondHalf[j++]);
      } else if (i < firstHalf.length) {
        order.push(firstHalf[i++]);
      } else if (j < secondHalf.length) {
        order.push(secondHalf[j++]);
      }
      takeFirst = !takeFirst;
    }
    return order.map((word) => ({ word, word_id: WORDS.indexOf(word) + 1 }));
  }

  async function preloadAudio(order) {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const buffers = new Map();
    let loaded = 0;
    const total = order.length;
    for (const item of order) {
      const url = `${STIM_PATH}/${item.word}.mp3`;
      setStatus(`音声プリロード中 ${loaded}/${total}: ${item.word}`);
      const res = await fetch(url);
      if (!res.ok) throw new Error(`音声が読み込めません: ${url}`);
      const arrBuf = await res.arrayBuffer();
      const buffer = await audioCtx.decodeAudioData(arrBuf);
      buffers.set(item.word, buffer);
      loaded += 1;
    }
    setStatus(`音声プリロード完了 (${loaded}/${total})`);
    return { audioCtx, buffers };
  }

  async function getMicStream() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      return stream;
    } catch (err) {
      throw new Error(`マイクアクセスに失敗しました: ${err.message}`);
    }
  }

  function showFixation() {
    messageEl.style.display = 'none';
    soundIconEl.style.display = 'none';
    fixationEl.style.display = 'block';
  }
  function showMessage(text) {
    fixationEl.style.display = 'none';
    soundIconEl.style.display = 'none';
    messageEl.textContent = text;
    messageEl.style.display = 'block';
  }
  function showSoundIcon() {
    fixationEl.style.display = 'none';
    messageEl.style.display = 'none';
    soundIconEl.style.display = 'block';
  }

  function makeRecorder(stream, mimeType) {
    const options = mimeType ? { mimeType } : undefined;
    const recorder = new MediaRecorder(stream, options);
    const chunks = [];
    recorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
    const start = () => new Promise((resolve) => { recorder.start(); resolve(); });
    const stopAfter = (ms) => new Promise((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunks, { type: recorder.mimeType }));
      setTimeout(() => recorder.stop(), ms);
    });
    return { recorder, start, stopAfter };
  }

  function buildCsv(rows) {
    const header = ['trial','word','word_id','playback_onset_ms','recording_start_ms','recording_end_ms','iti_ms','participant_id'];
    const lines = [header.join(',')];
    rows.forEach((r) => {
      lines.push([
        r.trial,
        r.word,
        r.word_id,
        r.playback_onset_ms.toFixed(3),
        r.recording_start_ms.toFixed(3),
        r.recording_end_ms.toFixed(3),
        r.iti_ms,
        r.participant_id,
      ].join(','));
    });
    return lines.join('\n');
  }

  async function runTask(participantId, order, audioCtx, buffers, micStream) {
    document.body.classList.add('running');
    showMessage('スペースキーで開始');
    setStatus('準備ができたらスペースキーで開始してください');

    await new Promise((resolve) => {
      const handler = (ev) => {
        if (ev.key === ' ') {
          document.removeEventListener('keydown', handler);
          resolve();
        }
      };
      document.addEventListener('keydown', handler);
    });

    if (audioCtx.state === 'suspended') {
      await audioCtx.resume();
    }

    const results = [];
    const recordings = [];
    const expStart = performance.now();

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : undefined;
    const recorderFactory = () => makeRecorder(micStream, mimeType);

    for (let idx = 0; idx < order.length; idx++) {
      const trial = order[idx];
      const buffer = buffers.get(trial.word);
      if (!buffer) throw new Error(`Audio buffer missing for ${trial.word}`);
      const source = audioCtx.createBufferSource();
      source.buffer = buffer;
      source.connect(audioCtx.destination);

      const { recorder, start, stopAfter } = recorderFactory();

      showSoundIcon();
      const now = performance.now();
      const playbackOnset = now - expStart;
      source.start();
      await start();
      const recStartMs = performance.now() - expStart;
      const blobPromise = stopAfter(RECORD_DURATION_MS);

      const recBlob = await blobPromise;
      const recEndMs = performance.now() - expStart;

      const filename = `${participantId}_${trial.word}.webm`;
      recordings.push({ filename, blob: recBlob });

      results.push({
        trial: idx + 1,
        word: trial.word,
        word_id: trial.word_id,
        playback_onset_ms: playbackOnset,
        recording_start_ms: recStartMs,
        recording_end_ms: recEndMs,
        iti_ms: ITI_MS,
        participant_id: participantId,
      });

      showFixation();
      setStatus(`試行 ${idx + 1}/${order.length} 完了。ITI 1.5秒`);
      await delay(ITI_MS);
    }

    showMessage('終了しました。お疲れさまでした。');
    setStatus('結果をZipでダウンロードできます。');
    return { results, recordings };
  }

  async function createZip(participantId, results, recordings) {
    const zip = new JSZip();
    const csv = buildCsv(results);
    zip.file(`results_${participantId}.csv`, csv);
    recordings.forEach(({ filename, blob }) => {
      zip.file(filename, blob);
    });
    const content = await zip.generateAsync({ type: 'blob' });
    return content;
  }

  preloadBtn.addEventListener('click', async () => {
    const participantId = participantInput.value.trim();
    if (!participantId) {
      setStatus('参加者IDを入力してください。');
      return;
    }

    preloadBtn.disabled = true;
    startBtn.classList.add('hidden');
    downloadBtn.classList.add('hidden');
    setLog('');

    try {
      const order = buildOrder(participantId);
      const { audioCtx, buffers } = await preloadAudio(order);
      setStatus('マイク許可を確認しています...');
      const micStream = await getMicStream();
      setStatus('プリロード完了。スペースキーで開始できます。');
      startBtn.classList.remove('hidden');
      showMessage('スペースキーで開始');

      startBtn.onclick = async () => {
        startBtn.classList.add('hidden');
        try {
          const { results, recordings } = await runTask(participantId, order, audioCtx, buffers, micStream);
          const zipBlob = await createZip(participantId, results, recordings);
          const url = URL.createObjectURL(zipBlob);
          downloadBtn.classList.remove('hidden');
          downloadBtn.onclick = () => {
            const a = document.createElement('a');
            a.href = url;
            a.download = `l2_to_l1_${participantId}.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
          };
        } catch (err) {
          console.error(err);
          setStatus(`エラー: ${err.message}`);
          preloadBtn.disabled = false;
        }
      };
    } catch (err) {
      console.error(err);
      setStatus(`エラー: ${err.message}`);
      preloadBtn.disabled = false;
    }
  });
})();
