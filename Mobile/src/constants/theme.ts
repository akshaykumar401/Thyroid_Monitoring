export const Colors = {
  // Brand Colors - extracted directly from the Thyroid Track Butterfly Logo
  primary: '#0D9488',       // Butterfly Vibrant Teal
  primaryLight: '#14B8A6',  // Luminous Teal
  primaryDark: '#0F766E',   // Deep Forest Teal
  primaryGlow: '#2DD4BF',   // Glowing Cyan-Teal
  
  // Secondary / Arrow Medical Cyan
  secondary: '#0284C7',     // Arrow Medical Cyan
  secondaryLight: '#38BDF8',// Bright Sky
  secondaryDark: '#0369A1', // Deep Navy Blue

  // Main UI Theme - Clean Clinical Healthtech
  bgApp: '#F1F6F9',         // Soft Clean Ice-White Background
  bgSurface: '#FFFFFF',     // Crisp White Cards
  bgCardSubtle: '#F8FAFC',  // Subtle Off-white Card
  borderSubtle: '#E2E8F0',  // Soft Slate Border
  borderActive: 'rgba(13, 148, 136, 0.35)', // Teal active border

  // Typography - Deep Navy
  textPrimary: '#0F2438',   // Deep Slate Navy (matches logo text)
  textSecondary: '#475569', // Muted Slate
  textMuted: '#64748B',     // Subtle Subtitle
  textLight: '#94A3B8',     // Light Slate
  textWhite: '#FFFFFF',     // Crisp White on Gradient Cards

  // Health Status Colors
  statusOptimal: '#10B981', // Emerald
  statusOptimalBg: '#ECFDF5',
  statusOptimalText: '#047857',
  
  statusWarning: '#F59E0B', // Amber
  statusWarningBg: '#FFFBEB',
  statusWarningText: '#B45309',

  statusInfo: '#0EA5E9',    // Sky
  statusInfoBg: '#F0F9FF',
  statusInfoText: '#0369A1',

  // Gradients
  gradientHero: ['#0C4A6E', '#0F3A5A', '#08253D'] as const,     // Deep Ocean Navy Hero
  gradientTeal: ['#0D9488', '#0284C7'] as const,                 // Vibrant Brand Gradient
  gradientMint: ['#F0FDFA', '#E0F2FE'] as const,                 // Soft Light Pastel Gradient
  gradientFlash: ['#07192A', '#0D2D4B', '#113B5F', '#0A2239'] as const, // Cinematic Flash Screen Gradient
};
