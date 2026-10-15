import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Animated } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useAudioPlayer, useAudioPlayerStatus, setAudioModeAsync } from 'expo-audio';
import { PlayIcon, PauseIcon } from '../Icons';

const VOICE_WAVE_PATTERN = [14, 24, 34, 44, 28, 40, 50, 34, 22, 38, 48, 32, 24, 40, 48, 28, 18];

interface VoiceBiomarkerPlayerProps {
  voiceUrl: string;
  voiceLabel: string;
  durationSec?: number;
}

export function VoiceBiomarkerPlayer({
  voiceUrl,
  voiceLabel,
  durationSec = 7.97,
}: VoiceBiomarkerPlayerProps) {
  const player = useAudioPlayer(voiceUrl);
  const status = useAudioPlayerStatus(player);

  const isPlaying = status.playing;
  const currentSec = status.currentTime || 0;
  const totalSec = status.duration && status.duration > 0 ? status.duration : durationSec;
  const progressPct = totalSec > 0 ? Math.min(1, Math.max(0, currentSec / totalSec)) : 0;

  // Animated wave oscillation when playing
  const waveAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Configure audio mode so audio plays through speakers on iOS & Android
    setAudioModeAsync({
      playsInSilentMode: true,
      shouldPlayInBackground: false,
    }).catch(() => {});
  }, []);

  useEffect(() => {
    let loop: Animated.CompositeAnimation | null = null;
    if (isPlaying) {
      loop = Animated.loop(
        Animated.sequence([
          Animated.timing(waveAnim, { toValue: 1, duration: 380, useNativeDriver: false }),
          Animated.timing(waveAnim, { toValue: 0, duration: 380, useNativeDriver: false }),
        ])
      );
      loop.start();
    } else {
      waveAnim.setValue(0);
    }
    return () => {
      if (loop) loop.stop();
    };
  }, [isPlaying]);

  const handleTogglePlay = () => {
    try {
      if (isPlaying) {
        player.pause();
      } else {
        if (currentSec >= totalSec - 0.2) {
          player.seekTo(0);
        }
        player.play();
      }
    } catch (err) {
      console.warn('Playback error:', err);
    }
  };

  const formatTime = (seconds: number) => {
    const total = Math.floor(seconds);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <View style={styles.cardBox}>
      {/* Waveform Visualization with Animated Bars */}
      <View style={styles.waveContainer}>
        <View style={styles.wavesRow}>
          {VOICE_WAVE_PATTERN.map((baseH, idx) => {
            const barProgress = (idx + 1) / VOICE_WAVE_PATTERN.length;
            const isPlayed = barProgress <= progressPct || (idx === 0 && currentSec > 0);

            const dynamicScale = waveAnim.interpolate({
              inputRange: [0, 1],
              outputRange: [1, idx % 2 === 0 ? 1.35 : 0.72],
            });

            return (
              <Animated.View
                key={idx}
                style={[
                  styles.waveBar,
                  {
                    height: baseH,
                    backgroundColor: isPlayed ? '#0D9488' : '#CBD5E1',
                    transform: [{ scaleY: dynamicScale }],
                  },
                ]}
              />
            );
          })}
        </View>

        {/* Playback progress bar track */}
        <View style={styles.progressTrack}>
          <View
            style={[
              styles.progressFill,
              { width: `${Math.round(progressPct * 100)}%` },
            ]}
          />
        </View>
      </View>

      {/* Audio Control Row */}
      <View style={styles.controlsRow}>
        <TouchableOpacity
          style={styles.playBtn}
          onPress={handleTogglePlay}
          activeOpacity={0.82}
        >
          <LinearGradient
            colors={isPlaying ? ['#E11D48', '#BE123C'] : ['#0D9488', '#0284C7']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.playBtnGrad}
          >
            {isPlaying ? (
              <PauseIcon size={20} color="#FFFFFF" />
            ) : (
              <PlayIcon size={20} color="#FFFFFF" />
            )}
          </LinearGradient>
        </TouchableOpacity>

        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={styles.titleText}>
            {isPlaying ? 'Streaming Cloudinary Audio' : 'Recorded Vocal Biomarker'}
          </Text>
          <Text style={styles.subText} numberOfLines={1}>
            {isPlaying
              ? 'Streaming from Cloudinary (dh7degaxv)'
              : `${voiceLabel} • Cloudinary live`}
          </Text>
        </View>

        <View style={styles.timePill}>
          <Text style={styles.timeText}>
            {formatTime(currentSec)} / {formatTime(totalSec)}
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  cardBox: {
    backgroundColor: '#F0FDFA',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: '#CCFBF1',
    marginTop: 4,
  },
  waveContainer: {
    marginBottom: 12,
  },
  wavesRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    height: 52,
    justifyContent: 'center',
    marginBottom: 8,
  },
  waveBar: {
    width: 4,
    borderRadius: 2,
  },
  progressTrack: {
    height: 4,
    backgroundColor: '#E2E8F0',
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#0D9488',
    borderRadius: 2,
  },
  controlsRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  playBtn: {
    shadowColor: '#0D9488',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 3,
  },
  playBtnGrad: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  titleText: {
    fontSize: 13,
    fontWeight: '800',
    color: '#0F2438',
  },
  subText: {
    fontSize: 10,
    color: '#64748B',
    marginTop: 2,
  },
  timePill: {
    backgroundColor: '#CCFBF1',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  timeText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#0D9488',
  },
});
