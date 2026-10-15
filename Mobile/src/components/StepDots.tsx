import React from 'react';
import { View, StyleSheet } from 'react-native';

export function StepDots({ current }: { current: number }) {
  return (
    <View style={styles.container}>
      {[1, 2, 3].map((n) => (
        <View
          key={n}
          style={[
            styles.dot,
            {
              width: n === current ? 22 : 7,
              backgroundColor: n === current ? '#0D9488' : '#CBD5E1',
            },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
  },
  dot: {
    height: 7,
    borderRadius: 3.5,
  },
});
