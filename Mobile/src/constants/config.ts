// Constant configuration for ThyroTrack IoT & Flask Backend

export const FLASK_SERVER_URL = 'https://thyroid-monitoring.vercel.app';

export interface DeviceConfig {
  readonly backendUrl: string;
  wifiSsid: string;
  wifiPassword?: string;
  deviceId: string;
  esp32Ip?: string;
  bleDeviceName: string;
  serviceUuid: string;
  configCharUuid: string;
  statusCharUuid: string;
}

export const DEFAULT_CONFIG: DeviceConfig = {
  backendUrl: FLASK_SERVER_URL,
  wifiSsid: 'Hanuman ',
  wifiPassword: '',
  deviceId: 'esp32-c3',
  bleDeviceName: 'ThyroTrack-ESP32',
  serviceUuid: '4fafc201-1fb5-459e-8fcc-c5c9c331914b',
  configCharUuid: 'beb5483e-36e1-4688-b7f5-ea07361b26a8',
  statusCharUuid: 'beb5483f-36e1-4688-b7f5-ea07361b26a8',
};

// In-memory runtime configuration store (backendUrl is constant and immutable)
let currentRuntimeConfig: DeviceConfig = { ...DEFAULT_CONFIG };

export const getRuntimeConfig = (): DeviceConfig => {
  return currentRuntimeConfig;
};

export const updateRuntimeConfig = (newConfig: Partial<Omit<DeviceConfig, 'backendUrl'>>): DeviceConfig => {
  currentRuntimeConfig = {
    ...currentRuntimeConfig,
    ...newConfig,
    backendUrl: FLASK_SERVER_URL, // Strictly constant
  };
  return currentRuntimeConfig;
};

// Shared Active Screening Session
export interface ScreeningSession {
  subjectId: string;
  recordingId?: string;
  bodyTemp?: number;
  pulseBpm?: number;
  qnaAnswers?: { questionId: number; category: string; question?: string; answer: string; score?: number }[];
  isQnaGiven?: boolean;
  cloudinaryAudioUrl?: string;
  mongodbId?: string;
}

export const CLOUDINARY_CLOUD_NAME = 'dh7degaxv';
export const DEFAULT_CLOUDINARY_VOICE_URL =
  'https://res.cloudinary.com/dh7degaxv/video/upload/v1791803233/thyrotrack_voice/thyrotrack_voice/patient_001_sample_vocal.wav';

let activeSession: ScreeningSession = {
  subjectId: 'patient_001',
  bodyTemp: 36.65,
  pulseBpm: 72,
  cloudinaryAudioUrl: DEFAULT_CLOUDINARY_VOICE_URL,
  qnaAnswers: [],
  isQnaGiven: false,
};

export const getScreeningSession = (): ScreeningSession => {
  return activeSession;
};

export const updateScreeningSession = (data: Partial<ScreeningSession>): ScreeningSession => {
  activeSession = {
    ...activeSession,
    ...data,
  };
  return activeSession;
};

/**
 * Health check ping to verify connectivity with the constant Flask backend.
 */
export const checkBackendHealth = async (): Promise<{ ok: boolean; message: string; data?: any }> => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);
    const res = await fetch(`${FLASK_SERVER_URL}/api/health`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      return { ok: true, message: 'Flask backend is online & responsive', data };
    }
    return { ok: false, message: `Server responded with status HTTP ${res.status}` };
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return { ok: false, message: 'Connection timed out (12s).' };
    }
    return { ok: false, message: err.message || 'Cannot reach Flask backend server' };
  }
};
