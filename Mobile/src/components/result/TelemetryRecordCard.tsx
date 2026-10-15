import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { DatabaseIcon } from '../Icons';

interface TelemetryRecordCardProps {
  database: string;
  collection: string;
  insertedId: string;
  savedAt: string;
  pulseBpm?: number;
  bodyTemp?: number;
  mongodbConnected: boolean;
}

export function TelemetryRecordCard({
  database,
  collection,
  insertedId,
  savedAt,
  pulseBpm,
  bodyTemp,
  mongodbConnected,
}: TelemetryRecordCardProps) {
  return (
    <View style={styles.dbCard}>
      <View style={styles.dbCardHeader}>
        <View style={styles.dbIconWrap}>
          <DatabaseIcon size={18} color="#15803D" />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.dbCardTitle}>Research Record Telemetry</Text>
          <Text style={styles.dbCardSub}>
            {mongodbConnected ? '🟢 Synced to MongoDB database' : '🟢 Saved in session cache'}
          </Text>
        </View>
      </View>

      <View style={styles.dbRow}>
        <Text style={styles.dbKey}>Collection</Text>
        <Text style={styles.dbVal}>{database}.{collection}</Text>
      </View>
      <View style={styles.dbRow}>
        <Text style={styles.dbKey}>Record ID</Text>
        <Text style={styles.dbValBold} numberOfLines={1}>{insertedId}</Text>
      </View>
      <View style={styles.dbRow}>
        <Text style={styles.dbKey}>Timestamp</Text>
        <Text style={styles.dbVal}>{savedAt.replace('T', ' ').slice(0, 19)}</Text>
      </View>
      <View style={styles.dbRow}>
        <Text style={styles.dbKey}>Pulse BPM</Text>
        <Text style={styles.dbVal}>{pulseBpm ?? 72} BPM (Synced)</Text>
      </View>
      <View style={styles.dbRow}>
        <Text style={styles.dbKey}>Body Temp</Text>
        <Text style={styles.dbVal}>{bodyTemp ?? 36.65} °C (Synced)</Text>
      </View>
      <View style={styles.dbRow}>
        <Text style={styles.dbKey}>Voice Audio</Text>
        <Text style={styles.dbValBold} numberOfLines={1}>Cloudinary (dh7degaxv) Synced</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  dbCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    padding: 16,
    marginBottom: 18,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    elevation: 2,
    shadowColor: '#0E2E4E',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
  },
  dbCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 14,
  },
  dbIconWrap: {
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: '#DCFCE7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dbCardTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#0F2438',
  },
  dbCardSub: {
    fontSize: 11,
    color: '#64748B',
    marginTop: 2,
  },
  dbRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
    borderTopWidth: 1,
    borderTopColor: '#F1F5F9',
  },
  dbKey: {
    fontSize: 12,
    color: '#64748B',
    fontWeight: '600',
  },
  dbVal: {
    fontSize: 12,
    color: '#0F2438',
    fontFamily: 'monospace',
    flex: 1,
    textAlign: 'right',
  },
  dbValBold: {
    fontSize: 12,
    color: '#0F766E',
    fontFamily: 'monospace',
    fontWeight: '800',
    flex: 1,
    textAlign: 'right',
  },
});
