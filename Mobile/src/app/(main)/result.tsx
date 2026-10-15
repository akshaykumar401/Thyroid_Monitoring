import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  StatusBar,
  ScrollView,
  Animated,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { SyncIcon, BulbIcon, ArrowRightIcon } from '../../components/Icons';
import { StepDots } from '../../components/StepDots';
import { SpinnerRing } from '../../components/result/SpinnerRing';
import { ThankYouHero } from '../../components/result/ThankYouHero';
import { QnaResponseCard } from '../../components/result/QnaResponseCard';
import { TelemetryRecordCard } from '../../components/result/TelemetryRecordCard';
import {
  FLASK_SERVER_URL,
  getScreeningSession,
  updateScreeningSession,
} from '../../constants/config';

// ──────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────
type SaveState = 'saving' | 'saved' | 'error';

interface SaveResult {
  insertedId: string;
  recordingId: string;
  qnaCount: number;
  mongodbConnected: boolean;
  database: string;
  collection: string;
  savedAt: string;
}

// ──────────────────────────────────────────────
// Result / Thank You Screen (Page 3 of 3)
// ──────────────────────────────────────────────
export default function ResultScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [saveState, setSaveState] = useState<SaveState>('saving');
  const [saveResult, setSaveResult] = useState<SaveResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>('');

  // Pulse animation for the success icon
  const pulseAnim = useRef(new Animated.Value(0.8)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (saveState === 'saved') {
      Animated.parallel([
        Animated.spring(pulseAnim, {
          toValue: 1,
          useNativeDriver: true,
          tension: 50,
          friction: 6,
        }),
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 400,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [saveState]);

  // ── Send QNA to backend on mount ──
  useEffect(() => {
    const session = getScreeningSession();

    const saveQna = async () => {
      setSaveState('saving');

      const payload = {
        subject_id: session.subjectId || 'patient_001',
        recording_id: session.recordingId || undefined,
        voice_cloudinary_url: session.cloudinaryAudioUrl,
        sensor: {
          body_temp: session.bodyTemp ?? 36.65,
          pulse_bpm: session.pulseBpm ?? 72,
        },
        qna_responses: session.qnaAnswers || [],
      };

      try {
        const res = await fetch(`${FLASK_SERVER_URL}/api/qna/save`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (res.ok) {
          const data = await res.json();
          const result: SaveResult = {
            insertedId: data.inserted_id || data.recording_id || 'local_cached',
            recordingId: data.recording_id || 'N/A',
            qnaCount: data.qna_count ?? (session.qnaAnswers?.length ?? 0),
            mongodbConnected: data.mongodb_connected ?? false,
            database: data.database || 'thyrotrack_db',
            collection: data.collection || 'records',
            savedAt: data.saved_at || new Date().toISOString(),
          };
          setSaveResult(result);
          setSaveState('saved');
          updateScreeningSession({
            mongodbId: result.insertedId,
            isQnaGiven: true,
            recordingId: data.recording_id || session.recordingId,
          });
        } else {
          const err = await res.json().catch(() => ({}));
          setErrorMsg(err.error || `Server error ${res.status}`);
          setSaveState('error');
        }
      } catch {
        // Offline / fallback cache
        const session2 = getScreeningSession();
        setSaveResult({
          insertedId: `qna_${Date.now()}`,
          recordingId: session2.recordingId || `qna_${Date.now()}`,
          qnaCount: session2.qnaAnswers?.length ?? 0,
          mongodbConnected: false,
          database: 'thyrotrack_db',
          collection: 'records',
          savedAt: new Date().toISOString(),
        });
        updateScreeningSession({ isQnaGiven: true });
        setSaveState('saved');
      }
    };

    saveQna();
  }, []);

  const session = getScreeningSession();
  const answers = session.qnaAnswers || [];

  // ── Render: Saving ──
  if (saveState === 'saving') {
    return (
      <View style={styles.centeredRoot}>
        <StatusBar barStyle="dark-content" backgroundColor="#F1F6F9" />
        <LinearGradient
          colors={['#E8F2F7', '#F1F6F9', '#F8FAFC']}
          style={StyleSheet.absoluteFill}
        />
        <SpinnerRing />
        <Text style={styles.savingTitle}>Saving Contribution…</Text>
        <Text style={styles.savingSubtitle}>
          Recording your responses and telemetry into our research database
        </Text>
      </View>
    );
  }

  // ── Render: Error ──
  if (saveState === 'error') {
    return (
      <View style={styles.centeredRoot}>
        <StatusBar barStyle="dark-content" backgroundColor="#F1F6F9" />
        <LinearGradient
          colors={['#E8F2F7', '#F1F6F9', '#F8FAFC']}
          style={StyleSheet.absoluteFill}
        />
        <View style={styles.errorIconWrap}>
          <Text style={styles.errorEmoji}>⚠️</Text>
        </View>
        <Text style={styles.errorTitle}>Submission Failed</Text>
        <Text style={styles.errorMsg}>{errorMsg || 'Could not reach Flask backend'}</Text>
        <TouchableOpacity
          style={styles.retryBtn}
          onPress={() => {
            setSaveState('saving');
            (async () => {
              const session3 = getScreeningSession();
              try {
                const res = await fetch(`${FLASK_SERVER_URL}/api/qna/save`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    subject_id: session3.subjectId || 'patient_001',
                    recording_id: session3.recordingId || undefined,
                    voice_cloudinary_url: session3.cloudinaryAudioUrl,
                    qna_responses: session3.qnaAnswers || [],
                    sensor: { body_temp: session3.bodyTemp ?? 36.65, pulse_bpm: session3.pulseBpm ?? 72 },
                  }),
                });
                if (res.ok) {
                  const d = await res.json();
                  setSaveResult({
                    insertedId: d.inserted_id || 'local_cached',
                    recordingId: d.recording_id || 'N/A',
                    qnaCount: d.qna_count ?? 0,
                    mongodbConnected: d.mongodb_connected ?? false,
                    database: d.database || 'thyrotrack_db',
                    collection: d.collection || 'records',
                    savedAt: d.saved_at || new Date().toISOString(),
                  });
                  setSaveState('saved');
                  updateScreeningSession({
                    isQnaGiven: true,
                    mongodbId: d.inserted_id,
                    recordingId: d.recording_id || session3.recordingId,
                  });
                } else {
                  const err = await res.json().catch(() => ({}));
                  setErrorMsg(err.error || `Server error ${res.status}`);
                  setSaveState('error');
                }
              } catch {
                setErrorMsg('Network unreachable');
                setSaveState('error');
              }
            })();
          }}
        >
          <Text style={styles.retryBtnText}>Retry</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => router.replace('/(main)/dashboard')}
          style={{ marginTop: 12 }}
        >
          <Text style={styles.backLinkText}>← Back to Dashboard</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Render: Success / Thank you ──
  const rc = saveResult!;

  return (
    <View style={styles.root}>
      <StatusBar barStyle="dark-content" backgroundColor="#F1F6F9" />
      <LinearGradient
        colors={['#E8F2F7', '#F1F6F9', '#F8FAFC']}
        style={StyleSheet.absoluteFill}
      />

      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 32 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Header ── */}
        <View style={styles.headerRow}>
          <View style={styles.headerLeft}>
            <Image
              source={require('../../../assets/images/logo.png')}
              style={styles.logoBadge}
            />
            <View>
              <View style={styles.brandRow}>
                <Text style={styles.brandDark}>Thyro</Text>
                <Text style={styles.brandTeal}>Track</Text>
              </View>
              <Text style={styles.stepLabel}>Step 3 of 3 • Research Contribution</Text>
            </View>
          </View>
          <StepDots current={3} />
        </View>

        {/* ── Thank You Hero Banner Component ── */}
        <ThankYouHero
          qnaCount={rc.qnaCount}
          pulseBpm={session.pulseBpm}
          bodyTemp={session.bodyTemp}
          fadeAnim={fadeAnim}
          pulseAnim={pulseAnim}
        />

        {/* ── Research Contribution Acknowledgement Card ── */}
        <View style={styles.appreciationCard}>
          <View style={styles.appreciationHeader}>
            <View style={styles.bulbIconWrap}>
              <BulbIcon size={20} color="#0D9488" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.appreciationTitle}>Contribution Acknowledged</Text>
              <Text style={styles.appreciationSub}>Thyroid Health Study • Data Synced</Text>
            </View>
          </View>
          <Text style={styles.appreciationText}>
            We sincerely appreciate your time and contribution. Your submitted answers and sensor telemetry provide vital data that helps our team develop accurate, non-invasive screening technologies.
          </Text>
        </View>

        {/* ── QNA Responses Section (Without symptom calculations) ── */}
        {answers.length > 0 && (
          <View style={styles.qnaSection}>
            <View style={styles.qnaSectionHeader}>
              <Text style={styles.qnaSectionTitle}>Questionnaire Responses</Text>
              <View style={styles.responseCountPill}>
                <Text style={styles.responseCountText}>{answers.length} Responses</Text>
              </View>
            </View>

            {answers.map((item, idx) => (
              <QnaResponseCard
                key={idx}
                index={idx}
                questionId={item.questionId}
                category={item.category}
                question={item.question}
                answer={item.answer}
              />
            ))}
          </View>
        )}

        {/* ── MongoDB Telemetry Record Info Component ── */}
        <TelemetryRecordCard
          database={rc.database}
          collection={rc.collection}
          insertedId={rc.insertedId}
          savedAt={rc.savedAt}
          pulseBpm={session.pulseBpm}
          bodyTemp={session.bodyTemp}
          mongodbConnected={rc.mongodbConnected}
        />

        {/* ── Actions ── */}
        <View style={styles.actionsRow}>
          <TouchableOpacity
            style={styles.newBtn}
            onPress={() => router.replace('/(main)/dashboard')}
            activeOpacity={0.8}
          >
            <ArrowRightIcon size={16} color="#0D9488" />
            <Text style={styles.newBtnText}>Back to Dashboard</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F1F6F9' },
  centeredRoot: {
    flex: 1,
    backgroundColor: '#F1F6F9',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  scrollContent: { paddingHorizontal: 22 },

  // ── Saving state ──
  savingTitle: { fontSize: 20, fontWeight: '800', color: '#0F2438', marginBottom: 6 },
  savingSubtitle: { fontSize: 13, color: '#64748B', textAlign: 'center' },

  // ── Error state ──
  errorIconWrap: { marginBottom: 16 },
  errorEmoji: { fontSize: 48 },
  errorTitle: { fontSize: 22, fontWeight: '900', color: '#EF4444', marginBottom: 8 },
  errorMsg: { fontSize: 13, color: '#64748B', textAlign: 'center', marginBottom: 24 },
  retryBtn: {
    backgroundColor: '#0D9488',
    paddingVertical: 13,
    paddingHorizontal: 36,
    borderRadius: 14,
  },
  retryBtnText: { color: '#FFF', fontWeight: '800', fontSize: 15 },
  backLinkText: { color: '#64748B', fontSize: 13, fontWeight: '600' },

  // ── Header ──
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  logoBadge: {
    width: 44,
    height: 44,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: '#0D9488',
    backgroundColor: '#FFFFFF',
  },
  brandRow: { flexDirection: 'row', alignItems: 'center' },
  brandDark: { fontSize: 20, fontWeight: '900', color: '#0F2438' },
  brandTeal: { fontSize: 20, fontWeight: '900', color: '#0D9488' },
  stepLabel: { fontSize: 11, color: '#64748B', fontWeight: '600', marginTop: 2 },

  // ── Appreciation Card ──
  appreciationCard: {
    backgroundColor: '#F0FDFA',
    borderRadius: 18,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#CCFBF1',
  },
  appreciationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 10,
  },
  bulbIconWrap: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: '#CCFBF1',
    alignItems: 'center',
    justifyContent: 'center',
  },
  appreciationTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F766E',
  },
  appreciationSub: {
    fontSize: 11,
    color: '#64748B',
    marginTop: 1,
  },
  appreciationText: {
    fontSize: 12.5,
    color: '#334155',
    lineHeight: 18,
  },

  // ── QNA section ──
  qnaSection: { marginBottom: 18 },
  qnaSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  qnaSectionTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#0F2438',
  },
  responseCountPill: {
    backgroundColor: '#CCFBF1',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
  },
  responseCountText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#0F766E',
  },

  // ── Actions ──
  actionsRow: { marginTop: 4 },
  newBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: '#FFFFFF',
    paddingVertical: 15,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#CBD5E1',
    elevation: 1,
  },
  newBtnText: { fontSize: 14, fontWeight: '800', color: '#0F2438' },
});