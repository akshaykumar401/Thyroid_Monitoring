import React, { useEffect } from 'react';
import { useRouter } from 'expo-router';
import { View, StyleSheet } from 'react-native';

/**
 * Entry: immediately routes to Page 1: Dashboard
 */
export default function Index() {
  const router = useRouter();

  useEffect(() => {
    // Navigate directly to Page 1: Dashboard
    const t = setTimeout(() => {
      router.replace('/(main)/dashboard');
    }, 50);
    return () => clearTimeout(t);
  }, []);

  return <View style={styles.blank} />;
}

const styles = StyleSheet.create({
  blank: { flex: 1, backgroundColor: '#F1F6F9' },
});
