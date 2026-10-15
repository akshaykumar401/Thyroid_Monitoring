import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated, LayoutChangeEvent } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

export function TempGauge({ value }: { value: number }) {
  // Map 0°C–100°C smoothly to 0%–100%
  const clamped = Math.min(100, Math.max(0, value));
  const targetPct = clamped; // 0 to 100%

  const animPct = useRef(new Animated.Value(targetPct)).current;
  const [trackWidth, setTrackWidth] = useState(0);

  useEffect(() => {
    Animated.spring(animPct, {
      toValue: targetPct,
      tension: 40,
      friction: 7,
      useNativeDriver: false,
    }).start();
  }, [targetPct]);

  const onTrackLayout = (e: LayoutChangeEvent) => {
    const w = e.nativeEvent.layout.width;
    if (w > 0) setTrackWidth(w);
  };

  const pointerLeft = animPct.interpolate({
    inputRange: [0, 100],
    outputRange: [0, trackWidth > 0 ? trackWidth : 280],
    extrapolate: 'clamp',
  });

  return (
    <View style={gaugeStyles.wrapper}>
      {/* Gauge Track */}
      <View style={gaugeStyles.track} onLayout={onTrackLayout}>
        <LinearGradient
          colors={['#38BDF8', '#10B981', '#F59E0B', '#EF4444']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={StyleSheet.absoluteFill}
        />
        {/* Animated pointer indicator */}
        <Animated.View
          style={[
            gaugeStyles.pointer,
            {
              transform: [{ translateX: pointerLeft }],
            },
          ]}
        />
      </View>

      {/* Range labels 0 - 100 */}
      <View style={gaugeStyles.labels}>
        <Text style={gaugeStyles.labelText}>0°C</Text>
        <Text style={[gaugeStyles.labelText, { color: '#0D9488', fontWeight: '800' }]}>
          50°C
        </Text>
        <Text style={gaugeStyles.labelText}>100°C</Text>
      </View>
    </View>
  );
}

const gaugeStyles = StyleSheet.create({
  wrapper: {
    marginVertical: 12,
  },
  track: {
    height: 10,
    borderRadius: 5,
    backgroundColor: '#E2E8F0',
    overflow: 'visible',
    position: 'relative',
  },
  pointer: {
    position: 'absolute',
    top: -5,
    left: -10,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#0F2438',
    borderWidth: 2.5,
    borderColor: '#FFFFFF',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3,
    elevation: 4,
  },
  labels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 6,
    paddingHorizontal: 2,
  },
  labelText: {
    fontSize: 10,
    color: '#94A3B8',
    fontWeight: '700',
  },
});
