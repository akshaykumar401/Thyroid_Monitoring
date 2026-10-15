import React, { useEffect, useRef } from 'react';
import { StyleSheet, Animated, Easing } from 'react-native';

export function SpinnerRing() {
  const spinAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.timing(spinAnim, {
        toValue: 1,
        duration: 900,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    ).start();
  }, []);

  const rotate = spinAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <Animated.View style={[styles.spinnerRing, { transform: [{ rotate }] }]} />
  );
}

const styles = StyleSheet.create({
  spinnerRing: {
    width: 54,
    height: 54,
    borderRadius: 27,
    borderWidth: 4,
    borderColor: '#0D9488',
    borderTopColor: 'transparent',
    marginBottom: 20,
  },
});
