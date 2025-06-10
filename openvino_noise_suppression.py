# openvino_noise_suppression.py

import os
import subprocess
import numpy as np
import soundfile as sf
import openvino.runtime as ov

# Update this path to where your IR really lives
BASE = os.path.abspath(os.path.dirname(__file__))
MODEL_XML = os.path.join(
    BASE, "models", "intel",
    "noise-suppression-denseunet-ll-0001", "FP16",
    "noise-suppression-denseunet-ll-0001.xml"
)
assert os.path.exists(MODEL_XML), f"Model not found: {MODEL_XML}"

class OpenVINONoiseSuppressor:
    def __init__(self, model_xml=MODEL_XML, device="CPU"):
        core = ov.Core()

        # 1) Read the raw model to inspect Parameter nodes
        model = core.read_model(model_xml)

        # 2) Identify the audio input parameter
        audio_param = model.inputs[0]
        self.in_name    = audio_param.get_any_name()
        shape           = audio_param.get_shape()  # e.g. [1, 128]
        if len(shape) != 2 or shape[0] != 1:
            raise RuntimeError(f"Unexpected audio input shape {shape}, expected [1,chunk]")
        self.chunk_size = shape[1]
        self.sample_rate= 16000

        # 3) Initialize state tensors from the same model.parameters list
        self.states = {}
        for param in model.inputs:
            pname = param.get_any_name()
            if pname and pname.startswith("inp_state_"):
                pshape = param.get_shape()
                self.states[pname] = np.zeros(pshape, np.float32)

        # 4) Compile the model for fast inference
        self.compiled = core.compile_model(model, device)

        print(f"[Suppressor] Loaded model '{MODEL_XML}' chunk_size={self.chunk_size}")

    def suppress_file(self, wav_in: str, wav_out: str):
        # 1) Force 16kHz mono WAV
        tmp = wav_in.replace(".wav", "_16k.wav")
        subprocess.run([
            "ffmpeg","-y","-i", wav_in,
            "-ar", str(self.sample_rate), "-ac", "1", tmp
        ], check=True, capture_output=True)

        audio, sr = sf.read(tmp)
        if sr != self.sample_rate:
            import librosa
            audio = librosa.resample(audio, sr, self.sample_rate)

        # 2) Pad audio to a multiple of chunk_size
        total   = len(audio)
        padded  = ((total + self.chunk_size - 1)//self.chunk_size)*self.chunk_size
        audio   = np.pad(audio, (0, padded-total), "constant")

        # 3) Inference in chunks
        out_chunks = []
        for start in range(0, padded, self.chunk_size):
            chunk = audio[start:start+self.chunk_size].astype(np.float32)
            # reshape to [1, chunk_size]
            tensor = chunk.reshape(1, self.chunk_size)

            # prepare inputs: audio + all state tensors
            inputs = {self.in_name: tensor, **self.states}
            results = self.compiled(inputs)

            # collect cleaned audio
            out_chunks.append(results["output"].squeeze())

            # update states for next chunk
            for output in results:
                name = output.get_any_name()
                if name.startswith("out_state_"):
                    self.states[name.replace("out_state_", "inp_state_")] = results[output]

        clean = np.concatenate(out_chunks)[:total]
        sf.write(wav_out, clean, self.sample_rate)
        os.remove(tmp)
