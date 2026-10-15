import React from 'react';
import Ionicons from '@expo/vector-icons/Ionicons';
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';

export { Ionicons, MaterialCommunityIcons };

interface IconProps {
  size?: number;
  color?: string;
}

export const HeartPulseIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <MaterialCommunityIcons name="heart-pulse" size={size} color={color} />
);

export const ChartCurveIcon: React.FC<IconProps> = ({ size = 20, color = '#38BDF8' }) => (
  <MaterialCommunityIcons name="chart-bell-curve" size={size} color={color} />
);

export const BluetoothIcon: React.FC<IconProps> = ({ size = 20, color = '#A78BFA' }) => (
  <Ionicons name="bluetooth" size={size} color={color} />
);

export const SyncIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <Ionicons name="sync" size={size} color={color} />
);

export const ArrowRightIcon: React.FC<IconProps> = ({ size = 20, color = '#5EEAD4' }) => (
  <Ionicons name="arrow-forward" size={size} color={color} />
);

export const SunIcon: React.FC<IconProps> = ({ size = 20, color = '#F59E0B' }) => (
  <Ionicons name="sunny" size={size} color={color} />
);

export const MoonIcon: React.FC<IconProps> = ({ size = 20, color = '#64748B' }) => (
  <Ionicons name="moon" size={size} color={color} />
);

export const SparklesIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <Ionicons name="sparkles" size={size} color={color} />
);

export const BellIcon: React.FC<IconProps> = ({ size = 20, color = '#CBD5E1' }) => (
  <Ionicons name="notifications-outline" size={size} color={color} />
);

export const ShieldCheckIcon: React.FC<IconProps> = ({ size = 20, color = '#10B981' }) => (
  <Ionicons name="shield-checkmark" size={size} color={color} />
);

export const WaveIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <MaterialCommunityIcons name="wave" size={size} color={color} />
);

export const MoleculeIcon: React.FC<IconProps> = ({ size = 20, color = '#38BDF8' }) => (
  <MaterialCommunityIcons name="molecule" size={size} color={color} />
);

export const LightningIcon: React.FC<IconProps> = ({ size = 20, color = '#A855F7' }) => (
  <MaterialCommunityIcons name="lightning-bolt" size={size} color={color} />
);

export const ShieldIcon: React.FC<IconProps> = ({ size = 20, color = '#F59E0B' }) => (
  <MaterialCommunityIcons name="shield-outline" size={size} color={color} />
);

export const AntennaIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <MaterialCommunityIcons name="access-point-network" size={size} color={color} />
);

export const BatteryIcon: React.FC<IconProps> = ({ size = 20, color = '#10B981' }) => (
  <Ionicons name="battery-charging" size={size} color={color} />
);

export const ThermometerIcon: React.FC<IconProps> = ({ size = 20, color = '#F59E0B' }) => (
  <MaterialCommunityIcons name="thermometer" size={size} color={color} />
);

export const WaterPercentIcon: React.FC<IconProps> = ({ size = 20, color = '#38BDF8' }) => (
  <MaterialCommunityIcons name="water-percent" size={size} color={color} />
);

export const PillIcon: React.FC<IconProps> = ({ size = 20, color = '#5EEAD4' }) => (
  <MaterialCommunityIcons name="pill" size={size} color={color} />
);

export const CheckmarkIcon: React.FC<IconProps> = ({ size = 20, color = '#FFFFFF' }) => (
  <Ionicons name="checkmark" size={size} color={color} />
);

export const CheckmarkCircleIcon: React.FC<IconProps> = ({ size = 20, color = '#FFFFFF' }) => (
  <Ionicons name="checkmark-circle" size={size} color={color} />
);

export const TimeIcon: React.FC<IconProps> = ({ size = 20, color = '#94A3B8' }) => (
  <Ionicons name="time-outline" size={size} color={color} />
);

export const BulbIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <Ionicons name="bulb" size={size} color={color} />
);

export const DocTextIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <Ionicons name="document-text-outline" size={size} color={color} />
);

export const ShareIcon: React.FC<IconProps> = ({ size = 20, color = '#A78BFA' }) => (
  <Ionicons name="share-social-outline" size={size} color={color} />
);

export const HomeIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <Ionicons name="home" size={size} color={color} />
);

export const PulseIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <Ionicons name="pulse" size={size} color={color} />
);

export const JournalIcon: React.FC<IconProps> = ({ size = 20, color = '#2DD4BF' }) => (
  <Ionicons name="journal" size={size} color={color} />
);

export const WifiIcon: React.FC<IconProps> = ({ size = 20, color = '#0D9488' }) => (
  <Ionicons name="wifi" size={size} color={color} />
);

export const LockIcon: React.FC<IconProps> = ({ size = 20, color = '#64748B' }) => (
  <Ionicons name="lock-closed-outline" size={size} color={color} />
);

export const EyeIcon: React.FC<IconProps> = ({ size = 20, color = '#64748B' }) => (
  <Ionicons name="eye-outline" size={size} color={color} />
);

export const EyeOffIcon: React.FC<IconProps> = ({ size = 20, color = '#64748B' }) => (
  <Ionicons name="eye-off-outline" size={size} color={color} />
);

export const ServerIcon: React.FC<IconProps> = ({ size = 20, color = '#0284C7' }) => (
  <MaterialCommunityIcons name="server-network" size={size} color={color} />
);

export const RefreshIcon: React.FC<IconProps> = ({ size = 20, color = '#0D9488' }) => (
  <Ionicons name="refresh" size={size} color={color} />
);

export const CloseIcon: React.FC<IconProps> = ({ size = 20, color = '#64748B' }) => (
  <Ionicons name="close" size={size} color={color} />
);

export const DatabaseIcon: React.FC<IconProps> = ({ size = 20, color = '#10B981' }) => (
  <MaterialCommunityIcons name="database-check" size={size} color={color} />
);

export const GoogleDriveIcon: React.FC<IconProps> = ({ size = 20, color = '#0284C7' }) => (
  <MaterialCommunityIcons name="google-drive" size={size} color={color} />
);

export const CloudUploadIcon: React.FC<IconProps> = ({ size = 20, color = '#0284C7' }) => (
  <Ionicons name="cloud-upload" size={size} color={color} />
);

export const PlayIcon: React.FC<IconProps> = ({ size = 20, color = '#FFFFFF' }) => (
  <Ionicons name="play" size={size} color={color} />
);

export const PauseIcon: React.FC<IconProps> = ({ size = 20, color = '#FFFFFF' }) => (
  <Ionicons name="pause" size={size} color={color} />
);

export const StopIcon: React.FC<IconProps> = ({ size = 20, color = '#FFFFFF' }) => (
  <Ionicons name="stop" size={size} color={color} />
);
