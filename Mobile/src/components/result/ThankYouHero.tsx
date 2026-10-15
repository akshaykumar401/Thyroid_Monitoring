import React from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { CheckmarkCircleIcon } from '../Icons';

interface ThankYouHeroProps {
  qnaCount: number;
  pulseBpm?: number;
  bodyTemp?: number;
  fadeAnim: Animated.Value;
  pulseAnim: Animated.Value;
}

export function ThankYouHero({
  qnaCount,
  pulseBpm,
  bodyTemp,
  fadeAnim,
  pulseAnim,
}: ThankYouHeroProps) {
  return (
    <Animated.View
      style={[
        styles.successBanner,
        { opacity: fadeAnim, transform: [{ scale: pulseAnim }] },
      ]}
    >
      <LinearGradient
        colors={['#0A3656', '#0E4973', '#082841']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.successGradient}
      >
        <View style={styles.checkCircle}>
          <CheckmarkCircleIcon size={38} color="#10B981" />
        </View>

        <Text style={styles.successTitle}>Thank You for Contributing!</Text>
        <Text style={styles.successSubtitle}>
          Thank you for contributing to our research project. Your questionnaire
          responses and telemetry data have been securely recorded.
        </Text>

        {/* Telemetry Stats Overview */}
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{qnaCount}</Text>
            <Text style={styles.statLabel}>Q&A Responses</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{pulseBpm ? `${pulseBpm} BPM` : '72 BPM'}</Text>
            <Text style={styles.statLabel}>Heart Rate</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{bodyTemp ? `${bodyTemp}°C` : '36.6°C'}</Text>
            <Text style={styles.statLabel}>Basal Temp</Text>
          </View>
        </View>
      </LinearGradient>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  successBanner: {
    borderRadius: 24,
    overflow: 'hidden',
    marginBottom: 16,
    elevation: 8,
    shadowColor: '#0E2E4E',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 14,
  },
  successGradient: {
    padding: 24,
    alignItems: 'center',
  },
  checkCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: 'rgba(16, 185, 129, 0.35)',
    marginBottom: 14,
  },
  successTitle: {
    fontSize: 22,
    fontWeight: '900',
    color: '#FFFFFF',
    marginBottom: 8,
    textAlign: 'center',
  },
  successSubtitle: {
    fontSize: 13,
    color: '#CBD5E1',
    textAlign: 'center',
    lineHeight: 19,
    marginBottom: 20,
    paddingHorizontal: 8,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    width: '100%',
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 16,
    paddingVertical: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  statItem: {
    alignItems: 'center',
  },
  statValue: {
    fontSize: 15,
    fontWeight: '900',
    color: '#FFFFFF',
  },
  statLabel: {
    fontSize: 10,
    color: '#94A3B8',
    fontWeight: '600',
    marginTop: 3,
  },
  statDivider: {
    width: 1,
    height: 28,
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
});
