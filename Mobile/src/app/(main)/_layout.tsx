import React from 'react';
import { Stack } from 'expo-router';

/**
 * 3-Page Flow:
 * 1. dashboard -> Sensor data & voice streaming + Start QNA round
 * 2. qna -> Clinical questionnaire
 * 3. result -> Confirmation of data saved in DB
 */
const MainStack = () => {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
        contentStyle: { backgroundColor: '#F1F6F9' },
      }}
    >
      <Stack.Screen name="dashboard" options={{ headerShown: false }} />
      <Stack.Screen name="qna" options={{ headerShown: false }} />
      <Stack.Screen name="result" options={{ headerShown: false, animation: 'fade_from_bottom' }} />
    </Stack>
  );
};

export default MainStack;