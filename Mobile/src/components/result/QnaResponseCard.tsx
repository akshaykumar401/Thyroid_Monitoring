import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { CheckmarkCircleIcon } from '../Icons';

interface QnaResponseCardProps {
  questionId?: number;
  index: number;
  category: string;
  question?: string;
  answer: string;
}

export function QnaResponseCard({
  questionId,
  index,
  category,
  question,
  answer,
}: QnaResponseCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.topRow}>
        <View style={styles.numBadge}>
          <Text style={styles.numText}>Q{questionId ?? index + 1}</Text>
        </View>
        <Text style={styles.catText}>{category}</Text>
      </View>

      {question ? <Text style={styles.questionText}>{question}</Text> : null}

      <View style={styles.answerBox}>
        <CheckmarkCircleIcon size={16} color="#0D9488" />
        <Text style={styles.answerText}>{answer}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    elevation: 1,
    shadowColor: '#0E2E4E',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  numBadge: {
    backgroundColor: '#F0FDFA',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderWidth: 1,
    borderColor: '#CCFBF1',
  },
  numText: {
    fontSize: 11,
    fontWeight: '800',
    color: '#0F766E',
  },
  catText: {
    flex: 1,
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
  },
  questionText: {
    fontSize: 12.5,
    color: '#475569',
    marginBottom: 8,
    lineHeight: 17,
  },
  answerBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#F8FAFC',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  answerText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0F2438',
    flex: 1,
  },
});
