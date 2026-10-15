import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  StatusBar,
  ScrollView,
  Animated,
  Easing,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ArrowRightIcon, CheckmarkCircleIcon, BulbIcon } from '../../components/Icons';
import { StepDots } from '../../components/StepDots';
import { QUESTIONS } from '../../data/questions';
import { updateScreeningSession } from '../../constants/config';

// ─────────────────────────────────────────────
// Q&A Questionnaire Screen (Page 2 of 3)
// ─────────────────────────────────────────────
export default function QnaScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, number>>({
    0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0
  });

  // Card slide animation on question change
  const slideAnim = useRef(new Animated.Value(0)).current;

  const animateNext = (cb: () => void) => {
    Animated.sequence([
      Animated.timing(slideAnim, {
        toValue: -30,
        duration: 150,
        useNativeDriver: true,
        easing: Easing.in(Easing.ease),
      }),
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 220,
        useNativeDriver: true,
        easing: Easing.out(Easing.ease),
      }),
    ]).start();
    setTimeout(cb, 100);
  };

  const currentQ = QUESTIONS[currentIndex];
  const progressPct = ((currentIndex + 1) / QUESTIONS.length) * 100;

  const handleSelect = (idx: number) => {
    setSelectedAnswers((prev) => ({ ...prev, [currentIndex]: idx }));
  };

  const handleNext = () => {
    if (currentIndex < QUESTIONS.length - 1) {
      animateNext(() => setCurrentIndex((p) => p + 1));
    } else {
      // Compile answers
      const formattedAnswers = QUESTIONS.map((q, idx) => {
        const optIdx = selectedAnswers[idx] ?? 0;
        const opt = q.options[optIdx] || q.options[0];
        return {
          questionId: q.id,
          category: q.category,
          question: q.title,
          answer: opt.label,
        };
      });

      updateScreeningSession({
        qnaAnswers: formattedAnswers,
        isQnaGiven: true,
      });

      router.push('/(main)/result');
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      animateNext(() => setCurrentIndex((p) => p - 1));
    }
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="dark-content" backgroundColor="#F1F6F9" />
      <LinearGradient colors={['#E4F0F7', '#EEF5FA', '#F8FAFC']} style={StyleSheet.absoluteFill} />
      <View style={styles.blobBR} />

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 32 }]}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Top bar ── */}
        <View style={styles.topBar}>
          <View style={styles.brandRow}>
            <Image source={require('../../../assets/images/logo.png')} style={styles.logoBadge} />
            <View>
              <View style={{ flexDirection: 'row' }}>
                <Text style={styles.brandDark}>Thyro</Text>
                <Text style={styles.brandTeal}>Track</Text>
              </View>
              <Text style={styles.brandSub}>Step 2 of 3 • Symptom Q&A</Text>
            </View>
          </View>
          <StepDots current={2} />
        </View>

        {/* ── Question counter + progress ── */}
        <View style={styles.progressSection}>
          <View style={styles.progressLabelRow}>
            <Text style={styles.progressLabel}>Question {currentIndex + 1} of {QUESTIONS.length}</Text>
            <View style={styles.counterBadge}>
              <Text style={styles.counterText}>{Math.round(progressPct)}%</Text>
            </View>
          </View>
          <View style={styles.progressTrack}>
            <LinearGradient
              colors={['#0D9488', '#0284C7']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={[styles.progressFill, { width: `${progressPct}%` as any }]}
            />
          </View>
        </View>

        {/* ── Question card (animated) ── */}
        <Animated.View style={{ transform: [{ translateX: slideAnim }] }}>
          <View style={styles.questionCard}>
            <View style={styles.categoryBadge}>
              <BulbIcon size={12} color="#0D9488" />
              <Text style={styles.categoryText}>{currentQ.category}</Text>
            </View>
            <Text style={styles.questionTitle}>{currentQ.title}</Text>
            <Text style={styles.questionSub}>{currentQ.subtitle}</Text>
          </View>

          {/* ── Options ── */}
          <View style={styles.optionsList}>
            {currentQ.options.map((opt, idx) => {
              const isSelected = selectedAnswers[currentIndex] === idx;
              return (
                <TouchableOpacity
                  key={idx}
                  style={[styles.optionCard, isSelected && styles.optionCardSelected]}
                  onPress={() => handleSelect(idx)}
                  activeOpacity={0.8}
                >
                  <View style={[styles.radioOuter, isSelected && styles.radioOuterSelected]}>
                    {isSelected && <View style={styles.radioDot} />}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.optionLabel, isSelected && styles.optionLabelSelected]}>
                      {opt.label}
                    </Text>
                    <Text style={styles.optionDesc}>{opt.desc}</Text>
                  </View>
                  {isSelected && (
                    <CheckmarkCircleIcon size={18} color="#0D9488" />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </Animated.View>

        {/* ── Navigation ── */}
        <View style={styles.navRow}>
          {currentIndex > 0 ? (
            <TouchableOpacity style={styles.prevBtn} onPress={handlePrev} activeOpacity={0.7}>
              <Text style={styles.prevBtnText}>‹ Prev</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={styles.prevBtn} onPress={() => router.replace('/(main)/dashboard')} activeOpacity={0.7}>
              <Text style={styles.prevBtnText}>‹ Dashboard</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity style={styles.nextBtn} onPress={handleNext} activeOpacity={0.85}>
            <LinearGradient
              colors={['#0D9488', '#0284C7']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={styles.nextBtnGrad}
            >
              <Text style={styles.nextBtnText}>
                {currentIndex === QUESTIONS.length - 1 ? 'Submit & Save to DB' : 'Next Question'}
              </Text>
              <ArrowRightIcon size={16} color="#FFF" />
            </LinearGradient>
          </TouchableOpacity>
        </View>

        {/* ── Bottom tip ── */}
        <View style={styles.tipBox}>
          <BulbIcon size={13} color="#0284C7" />
          <Text style={styles.tipText}>
            Answer based on your last 30 days. Honest responses improve screening accuracy.
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F1F6F9' },
  scroll: { paddingHorizontal: 20 },
  blobBR: {
    position: 'absolute',
    bottom: -80,
    right: -60,
    width: 220,
    height: 220,
    borderRadius: 110,
    backgroundColor: 'rgba(13,148,136,0.06)',
  },

  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 18,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  logoBadge: {
    width: 42,
    height: 42,
    borderRadius: 13,
    borderWidth: 1.5,
    borderColor: '#0D9488',
    backgroundColor: '#FFF',
  },
  brandDark: { fontSize: 22, fontWeight: '900', color: '#0F2438' },
  brandTeal: { fontSize: 22, fontWeight: '900', color: '#0D9488' },
  brandSub: { fontSize: 10, color: '#94A3B8', fontWeight: '600', marginTop: 1 },

  progressSection: { marginBottom: 18 },
  progressLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  progressLabel: { fontSize: 13, fontWeight: '700', color: '#334155' },
  counterBadge: {
    backgroundColor: '#CCFBF1',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
  },
  counterText: { fontSize: 12, fontWeight: '800', color: '#0F766E' },
  progressTrack: {
    height: 7,
    borderRadius: 4,
    backgroundColor: '#E2E8F0',
    overflow: 'hidden',
  },
  progressFill: { height: '100%', borderRadius: 4 },

  questionCard: {
    backgroundColor: '#FFF',
    borderRadius: 20,
    padding: 18,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    marginBottom: 14,
    shadowColor: '#0E2E4E',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.06,
    shadowRadius: 10,
    elevation: 2,
  },
  categoryBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: '#F0FDFA',
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: 8,
    alignSelf: 'flex-start',
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#CCFBF1',
  },
  categoryText: { fontSize: 11, fontWeight: '700', color: '#0F766E' },
  questionTitle: { fontSize: 17, fontWeight: '900', color: '#0F2438', lineHeight: 24, marginBottom: 6 },
  questionSub: { fontSize: 12, color: '#64748B', lineHeight: 17 },

  optionsList: { gap: 10, marginBottom: 20 },
  optionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#FFF',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1.5,
    borderColor: '#E2E8F0',
    shadowColor: '#0E2E4E',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1,
  },
  optionCardSelected: { borderColor: '#0D9488', backgroundColor: '#F0FDFA' },
  radioOuter: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: '#CBD5E1',
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioOuterSelected: { borderColor: '#0D9488' },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#0D9488' },
  optionLabel: { fontSize: 14, fontWeight: '800', color: '#0F2438', marginBottom: 2 },
  optionLabelSelected: { color: '#0F766E' },
  optionDesc: { fontSize: 12, color: '#64748B', lineHeight: 17 },

  navRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 },
  prevBtn: {
    flex: 1,
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderRadius: 16,
    backgroundColor: '#FFF',
    borderWidth: 1,
    borderColor: '#CBD5E1',
    alignItems: 'center',
  },
  prevBtnText: { fontSize: 14, fontWeight: '700', color: '#475569' },
  nextBtn: {
    flex: 2.5,
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#0D9488',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 5,
  },
  nextBtnGrad: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 15,
  },
  nextBtnText: { color: '#FFF', fontSize: 14, fontWeight: '800' },

  tipBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: '#F0F9FF',
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#BAE6FD',
  },
  tipText: { fontSize: 11, color: '#0369A1', lineHeight: 16, flex: 1, fontWeight: '600' },
});
