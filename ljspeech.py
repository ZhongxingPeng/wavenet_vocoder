from concurrent.futures import ProcessPoolExecutor
from functools import partial
import numpy as np
import os
import audio

from nnmnkwii import preprocessing as P
from hparams import hparams
from os.path import exists
import librosa

from hparams import hparams


def build_from_path(in_dir, out_dir, num_workers=1, tqdm=lambda x: x):
    executor = ProcessPoolExecutor(max_workers=num_workers)
    futures = []
    index = 1
    with open(os.path.join(in_dir, 'metadata.csv'), encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            wav_path = os.path.join(in_dir, 'wavs', '%s.wav' % parts[0])
            text = parts[2]
            futures.append(executor.submit(
                partial(_process_utterance, out_dir, index, wav_path, text)))
            index += 1
    return [future.result() for future in tqdm(futures)]


def _process_utterance(out_dir, index, wav_path, text):
    # Load the audio to a numpy array:
    wav = audio.load_wav(wav_path)

    # Mu-law quantize
    quantized = P.mulaw_quantize(wav)

    # Trim silences
    start, end = audio.start_and_end_indices(quantized, hparams.silence_threshold)
    quantized = quantized[start:end]
    wav = wav[start:end]

    # Compute a mel-scale spectrogram from the trimmed wav:
    # (N, D)
    mel_spectrogram = audio.melspectrogram(wav).astype(np.float32).T
    # lws pads zeros internally before performing stft
    # this is needed to adjast time resolution between audio and mel-spectrogram
    l, r = audio.lws_pad_lr(wav, hparams.fft_size, audio.get_hop_size())

    # zero pad for quantized signal
    quantized = np.pad(quantized, (l, r), mode="constant",
                       constant_values=P.mulaw_quantize(0))
    N = mel_spectrogram.shape[0]
    assert len(quantized) >= N * audio.get_hop_size()

    # time resolution adjastment
    # ensure length of raw audio is multiple of hop_size so that we can use
    # transposed convolution to upsample
    quantized = quantized[:N * audio.get_hop_size()]
    assert len(quantized) % audio.get_hop_size() == 0

    timesteps = len(quantized)

    # Write the spectrograms to disk:
    audio_filename = 'ljspeech-audio-%05d.npy' % index
    mel_filename = 'ljspeech-mel-%05d.npy' % index
    np.save(os.path.join(out_dir, audio_filename),
            quantized.astype(np.int16), allow_pickle=False)
    np.save(os.path.join(out_dir, mel_filename),
            mel_spectrogram.astype(np.float32), allow_pickle=False)

    # Return a tuple describing this training example:
    return (audio_filename, mel_filename, timesteps, text)
