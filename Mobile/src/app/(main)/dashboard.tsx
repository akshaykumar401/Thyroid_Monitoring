import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  Animated,
  StatusBar,
  ScrollView,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter, useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  ThermometerIcon,
  HeartPulseIcon,
  WaveIcon,
  ArrowRightIcon,
  SyncIcon,
  SparklesIcon,
  CheckmarkCircleIcon,
} from '../../components/Icons';
import { StepDots } from '../../components/StepDots';
import { TempGauge } from '../../components/dashboard/TempGauge';
import { PulseGauge } from '../../components/dashboard/PulseGauge';
import { EcgWave } from '../../components/dashboard/EcgWave';
import { VoiceBiomarkerPlayer } from '../../components/dashboard/VoiceBiomarkerPlayer';
import {
  FLASK_SERVER_URL,
  getScreeningSession,
  updateScreeningSession,
} from '../../constants/config';

// ─────────────────────────────────────────────
// Dashboard Screen (Page 1 of 3)
// ─────────────────────────────────────────────
export default function DashboardScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();


  // Initialize directly from active screening session
  const initialSession = getScreeningSession();
  const [measuring, setMeasuring] = useState(false);
  const [pulseBPM, setPulseBPM] = useState(initialSession.pulseBpm || 0);
  const [bodyTemp, setBodyTemp] = useState(initialSession.bodyTemp || 0);
  const [fetchedLive, setFetchedLive] = useState(false);
  const [dataReady, setDataReady] = useState(true);

  const [isQnaGiven, setIsQnaGiven] = useState(
    Boolean(initialSession.qnaAnswers && initialSession.qnaAnswers.length > 0)
  );

  // Live voice recording from Cloudinary & Backend
  const [voiceUrl, setVoiceUrl] = useState(
    initialSession.cloudinaryAudioUrl ||
    'https://res.cloudinary.com/dh7degaxv/video/upload/v1792073746/thyrotrack_voice/thyrotrack_voice/subject_001_audio_20261015_141546_esp32_60a90110.wav'
  );
  const [voiceLabel, setVoiceLabel] = useState('audio_20261015_141546_esp32_60a90110.wav');
  const [voiceRecordingId, setVoiceRecordingId] = useState(initialSession.recordingId || 'esp32_60a90110');
  const [voiceDuration, setVoiceDuration] = useState(3.856);

  // Mutable ref so async polling always accesses latest recording ID without stale closure
  const recordingIdRef = useRef<string>(initialSession.recordingId || 'esp32_60a90110');

  // Heartbeat animation
  const heartScale = useRef(new Animated.Value(1)).current;
  // Entrance animation
  const fadeAnim = useRef(new Animated.Value(0)).current;

  const fetchSensor = useCallback(async () => {
    try {
      const res = await fetch(`${FLASK_SERVER_URL}/api/sensor/latest?_t=${Date.now()}`, {
        headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' },
      });
      if (res.ok) {
        const d = await res.json();
        const rawBpm = d.average_bpm ?? d.pulse_bpm ?? d.bpm;
        const rawTemp = d.average_temperature_c ?? d.body_temp ?? d.temperature;

        // Properly handle 0 BPM when no pulse/finger is detected
        const bpmVal = typeof rawBpm === 'number' && !isNaN(rawBpm) && rawBpm >= 0 ? Math.round(rawBpm) : 0;
        const tempVal = typeof rawTemp === 'number' && !isNaN(rawTemp) && rawTemp > 0 ? parseFloat(rawTemp.toFixed(2)) : 0;

        setPulseBPM(bpmVal);
        if (tempVal > 0) {
          setBodyTemp(tempVal);
        }
        if (d.recording_id) {
          setVoiceRecordingId(d.recording_id);
          recordingIdRef.current = d.recording_id;
        }
        updateScreeningSession({
          bodyTemp: tempVal > 0 ? tempVal : undefined,
          pulseBpm: bpmVal,
          recordingId: d.recording_id || recordingIdRef.current,
        });
        setFetchedLive(true);
        setDataReady(true);
      }
    } catch {
      // Graceful fallback
    }
  }, []);

  const fetchVoice = useCallback(async () => {
    try {
      const res = await fetch(`${FLASK_SERVER_URL}/api/audio/latest-info?_t=${Date.now()}`, {
        headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' },
      });
      if (res.ok) {
        const d = await res.json();
        if (d.cloudinary_url) {
          setVoiceUrl(d.cloudinary_url);
          if (d.filename) setVoiceLabel(d.filename);
          if (d.recording_id) {
            setVoiceRecordingId(d.recording_id);
            recordingIdRef.current = d.recording_id;
          }
          if (d.duration_seconds) setVoiceDuration(d.duration_seconds);
          updateScreeningSession({
            cloudinaryAudioUrl: d.cloudinary_url,
            recordingId: d.recording_id,
          });
        }
      }
    } catch {
      // Graceful fallback
    }
  }, []);

  const checkQna = useCallback(async () => {
    try {
      const recId = recordingIdRef.current || getScreeningSession().recordingId || '';
      const url = recId
        ? `${FLASK_SERVER_URL}/api/qna/status?recording_id=${recId}&_t=${Date.now()}`
        : `${FLASK_SERVER_URL}/api/qna/status?_t=${Date.now()}`;
      const res = await fetch(url, {
        headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' },
      });
      if (res.ok) {
        const d = await res.json();
        const currentSession = getScreeningSession();
        const hasLocalAnswers = Boolean(currentSession.qnaAnswers && currentSession.qnaAnswers.length > 0);
        if (d.is_qna_given || hasLocalAnswers) {
          setIsQnaGiven(true);
          updateScreeningSession({ isQnaGiven: true });
        } else {
          setIsQnaGiven(false);
          updateScreeningSession({ isQnaGiven: false });
        }
      }
    } catch {
      // Retain current session state on network error
    }
  }, []);

  // Re-check session and backend whenever Dashboard screen comes into focus
  useFocusEffect(
    useCallback(() => {
      const session = getScreeningSession();
      const hasAnswers = Boolean(session.qnaAnswers && session.qnaAnswers.length > 0);
      setIsQnaGiven(hasAnswers);
      fetchSensor();
      fetchVoice();
      checkQna();
    }, [fetchSensor, fetchVoice, checkQna])
  );

  useEffect(() => {
    Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: true }).start();

    const heartLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(heartScale, { toValue: 1.2, duration: 320, useNativeDriver: true }),
        Animated.timing(heartScale, { toValue: 1, duration: 440, useNativeDriver: true }),
        Animated.delay(300),
      ])
    );
    heartLoop.start();

    // Check local session state
    const session = getScreeningSession();
    if (session.isQnaGiven || (session.qnaAnswers && session.qnaAnswers.length > 0)) {
      setIsQnaGiven(true);
    }

    fetchSensor();
    fetchVoice();
    checkQna();
    const poll = setInterval(() => {
      fetchSensor();
      fetchVoice();
      checkQna();
    }, 3000);

    return () => {
      clearInterval(poll);
      heartLoop.stop();
    };
  }, [fetchSensor, fetchVoice, checkQna]);

  const handleRefresh = async () => {
    setMeasuring(true);
    try {
      await Promise.all([fetchSensor(), fetchVoice(), checkQna()]);
    } finally {
      setMeasuring(false);
    }
  };

  const handleStartQna = () => {
    updateScreeningSession({
      bodyTemp,
      pulseBpm: pulseBPM,
      cloudinaryAudioUrl: voiceUrl,
      recordingId: voiceRecordingId,
    });
    router.push('/(main)/qna');
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="dark-content" backgroundColor="#F1F6F9" />
      <LinearGradient colors={['#E4F0F7', '#EEF5FA', '#F8FAFC']} style={StyleSheet.absoluteFill} />
      <View style={styles.blobTL} />

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 32 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Top Bar ── */}
        <Animated.View style={[styles.topBar, { opacity: fadeAnim }]}>
          <View style={styles.brandRow}>
            <Image
              source={require('../../../assets/images/logo.png')}
              style={styles.logoBadge}
            />
            <View>
              <View style={{ flexDirection: 'row' }}>
                <Text style={styles.brandDark}>Thyro</Text>
                <Text style={styles.brandTeal}>Track</Text>
              </View>
              <Text style={styles.brandSub}>Step 1 of 3 • Dashboard</Text>
            </View>
          </View>
          <StepDots current={1} />
        </Animated.View>

        {/* ── Title Header ── */}
        <Animated.View style={{ opacity: fadeAnim, marginBottom: 16 }}>
          <Text style={styles.pageTitle}>Health Dashboard</Text>
          <Text style={styles.pageSub}>
            Real-time biosensors, basal temperature telemetry & vocal biomarkers.
          </Text>
        </Animated.View>

        {/* ── Status Bar ── */}
        <View style={styles.statusBar}>
          <View style={styles.liveDot} />
          <Text style={styles.statusBarText}>
            {fetchedLive ? 'Node: esp32-c3 • Connected & Live Synced' : 'Node: esp32-c3 • Telemetry stream ready'}
          </Text>
          <TouchableOpacity style={styles.refreshBtn} onPress={handleRefresh} activeOpacity={0.8}>
            <SyncIcon size={12} color="#0D9488" />
            <Text style={styles.refreshText}>{measuring ? 'Reading…' : 'Refresh'}</Text>
          </TouchableOpacity>
        </View>

        {/* ── Sensor Card 1: Basal Body Temperature ── */}
        <View style={styles.sensorCard}>
          <View style={styles.cardHeader}>
            <View style={[styles.iconWrap, { backgroundColor: '#FEF3C7' }]}>
              <ThermometerIcon size={20} color="#D97706" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>Basal Body Temperature</Text>
              <Text style={styles.cardProbe}>Dallas DS18B20 Digital Sensor</Text>
            </View>
            <View style={styles.normalPill}>
              <Text style={styles.normalPillText}>
                {bodyTemp < 36.3 ? 'Low' : bodyTemp > 37.2 ? 'High' : 'Normal'}
              </Text>
            </View>
          </View>

          <View style={styles.metricRow}>
            <Text style={styles.metricBig}>{bodyTemp.toFixed(2)}</Text>
            <Text style={styles.metricUnit}>°C</Text>
            <Text style={styles.metricAlt}> ({(bodyTemp * 1.8 + 32).toFixed(1)}°F)</Text>
          </View>

          {/* Clean, responsive animated gauge */}
          <TempGauge value={bodyTemp} />
        </View>

        {/* ── Sensor Card 2: Cardiovascular Pulse ── */}
        <View style={styles.sensorCard}>
          <View style={styles.cardHeader}>
            <Animated.View
              style={[
                styles.iconWrap,
                { backgroundColor: '#FFE4E6', transform: [{ scale: heartScale }] },
              ]}
            >
              <HeartPulseIcon size={20} color="#E11D48" />
            </Animated.View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>Cardiovascular Pulse</Text>
              <Text style={styles.cardProbe}>ADC1 Photoplethysmograph (PPG)</Text>
            </View>
            <View style={styles.normalPill}>
              <Text style={styles.normalPillText}>Resting Normal</Text>
            </View>
          </View>

          <View style={styles.metricRow}>
            <Text style={styles.metricBig}>{pulseBPM}</Text>
            <Text style={styles.metricUnit}>BPM</Text>
            <Text style={styles.metricAlt}> • 30s Sinus Rhythm</Text>
          </View>

          {/* Pulse Gauge in BPM (0 - 200 BPM) */}
          <PulseGauge value={pulseBPM} />

          {/* ECG graph strip */}
          <View style={styles.ecgContainer}>
            <EcgWave />
          </View>
        </View>

        {/* ── Sensor Card 3: Voice Acoustic Biomarker ── */}
        <View style={styles.sensorCard}>
          <View style={styles.cardHeader}>
            <View style={[styles.iconWrap, { backgroundColor: '#CCFBF1' }]}>
              <WaveIcon size={20} color="#0D9488" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>Vocal Acoustic Biomarker</Text>
              <Text style={styles.cardProbe}>INMP441 I2S Digital Mic • 16 kHz WAV</Text>
            </View>
            <View style={[styles.normalPill, { backgroundColor: '#DCFCE7' }]}>
              <Text style={[styles.normalPillText, { color: '#15803D' }]}>Cloudinary • dh7degaxv</Text>
            </View>
          </View>

          {/* Playable vocal biomarker audio */}
          <VoiceBiomarkerPlayer
            key={voiceUrl}
            voiceUrl={voiceUrl}
            voiceLabel={voiceLabel}
            durationSec={voiceDuration}
          />
        </View>

        {/* ── Completion status banner ── */}
        {dataReady && (
          <View style={styles.summaryBanner}>
            <View style={styles.summaryCheckWrap}>
              <CheckmarkCircleIcon size={22} color="#10B981" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.summaryTitle}>Hardware Telemetry Synchronized</Text>
              <Text style={styles.summarySub}>
                Basal temp, pulse telemetry & Cloudinary vocal sample ready.
              </Text>
            </View>
            <View style={styles.readyBadge}>
              <Text style={styles.readyText}>READY</Text>
            </View>
          </View>
        )}

        {/* ── Dynamic QNA Action Button (Based on isQnaGiven) ── */}
        {!isQnaGiven ? (
          <TouchableOpacity
            style={styles.continueBtn}
            onPress={handleStartQna}
            activeOpacity={0.85}
          >
            <LinearGradient
              colors={['#0F2438', '#1E3A5F']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={styles.continueGrad}
            >
              <SparklesIcon size={18} color="#5EEAD4" />
              <Text style={styles.continueText}>Complete Clinical Q&A</Text>
              <ArrowRightIcon size={18} color="#FFFFFF" />
            </LinearGradient>
          </TouchableOpacity>
        ) : (
          <View style={styles.qnaCompletedCard}>
            <View style={styles.qnaCompletedHeader}>
              <View style={styles.qnaCompletedIcon}>
                <CheckmarkCircleIcon size={22} color="#10B981" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.qnaCompletedTitle}>Clinical Q&A Completed</Text>
                <Text style={styles.qnaCompletedSub}>
                  Your responses are saved in MongoDB Atlas
                </Text>
              </View>
            </View>

            <View style={styles.qnaCompletedActions}>
              <TouchableOpacity
                style={styles.viewResultBtn}
                onPress={() => {
                  updateScreeningSession({
                    bodyTemp,
                    pulseBpm: pulseBPM,
                    cloudinaryAudioUrl: voiceUrl,
                    recordingId: voiceRecordingId,
                  });
                  router.push('/(main)/result');
                }}
                activeOpacity={0.85}
              >
                <LinearGradient
                  colors={['#0D9488', '#0284C7']}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 0 }}
                  style={styles.viewResultGrad}
                >
                  <Text style={styles.viewResultText}>View Submitted Responses</Text>
                  <ArrowRightIcon size={15} color="#FFFFFF" />
                </LinearGradient>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.retakeBtn}
                onPress={handleStartQna}
                activeOpacity={0.7}
              >
                <Text style={styles.retakeText}>Retake Clinical Q&A</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F1F6F9' },
  scroll: { paddingHorizontal: 20 },

  blobTL: {
    position: 'absolute',
    top: -60,
    left: -60,
    width: 220,
    height: 220,
    borderRadius: 110,
    backgroundColor: '#CCFBF1',
    opacity: 0.45,
  },

  // ── Top Bar ──
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  logoBadge: {
    width: 42,
    height: 42,
    borderRadius: 13,
    borderWidth: 1.5,
    borderColor: '#0D9488',
    backgroundColor: '#FFFFFF',
  },
  brandDark: { fontSize: 20, fontWeight: '900', color: '#0F2438' },
  brandTeal: { fontSize: 20, fontWeight: '900', color: '#0D9488' },
  brandSub: { fontSize: 11, color: '#64748B', fontWeight: '600' },

  // ── Page Titles ──
  pageTitle: { fontSize: 24, fontWeight: '900', color: '#0F2438', letterSpacing: -0.5 },
  pageSub: { fontSize: 13, color: '#64748B', marginTop: 4, lineHeight: 18 },

  // ── Status Bar ──
  statusBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    gap: 8,
  },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#10B981' },
  statusBarText: { flex: 1, fontSize: 11, color: '#475569', fontWeight: '600' },
  refreshBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    backgroundColor: '#F0FDFA',
  },
  refreshText: { fontSize: 11, fontWeight: '700', color: '#0D9488' },

  // ── Sensor Cards ──
  sensorCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    elevation: 2,
    shadowColor: '#0E2E4E',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardTitle: { fontSize: 14, fontWeight: '800', color: '#0F2438' },
  cardProbe: { fontSize: 10.5, color: '#64748B', marginTop: 1 },
  normalPill: {
    backgroundColor: '#DCFCE7',
    paddingHorizontal: 9,
    paddingVertical: 3.5,
    borderRadius: 8,
  },
  normalPillText: { fontSize: 11, fontWeight: '700', color: '#15803D' },

  metricRow: { flexDirection: 'row', alignItems: 'baseline', marginBottom: 4 },
  metricBig: { fontSize: 32, fontWeight: '900', color: '#0F2438', letterSpacing: -1 },
  metricUnit: { fontSize: 18, fontWeight: '800', color: '#0D9488', marginLeft: 4 },
  metricAlt: { fontSize: 12, color: '#94A3B8', fontWeight: '600', marginLeft: 6 },

  ecgContainer: {
    backgroundColor: '#FFF1F2',
    borderRadius: 10,
    paddingVertical: 8,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },

  // ── Summary Banner ──
  summaryBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F0FDF4',
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: '#BBF7D0',
    marginBottom: 16,
    gap: 10,
  },
  summaryCheckWrap: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: '#DCFCE7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  summaryTitle: { fontSize: 12.5, fontWeight: '800', color: '#166534' },
  summarySub: { fontSize: 11, color: '#4B7C59', marginTop: 1 },
  readyBadge: {
    backgroundColor: '#166534',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  readyText: { fontSize: 9.5, fontWeight: '900', color: '#FFFFFF', letterSpacing: 0.5 },

  // ── Continue Button ──
  continueBtn: {
    borderRadius: 16,
    overflow: 'hidden',
    elevation: 4,
    shadowColor: '#0F2438',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
  },
  continueGrad: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingVertical: 16,
    paddingHorizontal: 20,
  },
  continueText: { fontSize: 15, fontWeight: '800', color: '#FFFFFF' },

  // ── QNA Completed Card ──
  qnaCompletedCard: {
    backgroundColor: '#F0FDF4',
    borderRadius: 18,
    padding: 16,
    borderWidth: 1.5,
    borderColor: '#BBF7D0',
    elevation: 2,
    shadowColor: '#10B981',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
  },
  qnaCompletedHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  qnaCompletedIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#DCFCE7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  qnaCompletedTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: '#15803D',
  },
  qnaCompletedSub: {
    fontSize: 11,
    color: '#475569',
    marginTop: 1,
  },
  qnaCompletedActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  viewResultBtn: {
    flex: 1,
    borderRadius: 12,
    overflow: 'hidden',
  },
  viewResultGrad: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 12,
    paddingHorizontal: 14,
  },
  viewResultText: {
    fontSize: 13,
    fontWeight: '800',
    color: '#FFFFFF',
  },
  retakeBtn: {
    paddingVertical: 11,
    paddingHorizontal: 14,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#CBD5E1',
  },
  retakeText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#475569',
  },
});
