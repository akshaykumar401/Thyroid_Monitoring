export interface QuestionOption {
  label: string;
  desc: string;
  score: number;
}

export interface Question {
  id: number;
  category: string;
  title: string;
  subtitle: string;
  options: QuestionOption[];
}

export const QUESTIONS: Question[] = [
  {
    id: 1,
    category: 'Energy & Metabolic Rhythm',
    title: 'How would you describe your typical daily fatigue level?',
    subtitle: 'Thyroid hormones influence energy levels and metabolism.',
    options: [
      {
        label: 'High Vitality & Alert',
        desc: 'Feel energetic throughout the day.',
        score: 0,
      },
      {
        label: 'Mild Afternoon Slump',
        desc: 'Feel tired occasionally during the day.',
        score: 1,
      },
      {
        label: 'Persistent Fatigue',
        desc: 'Frequently feel tired even after adequate sleep.',
        score: 3,
      },
    ],
  },
  {
    id: 2,
    category: 'Thermal Regulation',
    title: 'Do you experience unusual sensitivity to cold?',
    subtitle: 'Thyroid hormones help regulate body temperature.',
    options: [
      {
        label: 'Comfortable',
        desc: 'Usually comfortable at normal temperatures.',
        score: 0,
      },
      {
        label: 'Occasionally Cold',
        desc: 'Sometimes feel colder than other people.',
        score: 1,
      },
      {
        label: 'Frequently Cold',
        desc: 'Often feel unusually cold in normal conditions.',
        score: 3,
      },
    ],
  },
  {
    id: 3,
    category: 'Weight & Body Composition',
    title: 'Have you noticed unexplained weight changes in the past 3 months?',
    subtitle: 'Thyroid disorders can affect metabolism and body weight.',
    options: [
      {
        label: 'No Significant Change',
        desc: 'My weight has remained relatively stable.',
        score: 0,
      },
      {
        label: 'Small Change',
        desc: 'I have noticed a slight weight change.',
        score: 1,
      },
      {
        label: 'Significant Change',
        desc: 'My weight has changed without an obvious reason.',
        score: 3,
      },
    ],
  },
  {
    id: 4,
    category: 'Voice Analysis',
    title: 'Have you noticed a persistent change in your voice?',
    subtitle: 'Voice changes may occur with some thyroid conditions.',
    options: [
      {
        label: 'No Voice Change',
        desc: 'My voice sounds normal for me.',
        score: 0,
      },
      {
        label: 'Occasional Change',
        desc: 'My voice sometimes sounds rough or hoarse.',
        score: 1,
      },
      {
        label: 'Persistent Change',
        desc: 'My voice has remained hoarse or deeper for weeks.',
        score: 3,
      },
    ],
  },
  {
    id: 5,
    category: 'Neck & Thyroid Symptoms',
    title: 'Have you noticed swelling or a lump in the front of your neck?',
    subtitle: 'Swelling in this area can have several causes and needs medical assessment.',
    options: [
      {
        label: 'No',
        desc: 'I have not noticed any swelling or lump.',
        score: 0,
      },
      {
        label: 'Unsure',
        desc: 'I am not sure whether swelling is present.',
        score: 1,
      },
      {
        label: 'Yes',
        desc: 'I have noticed swelling or a lump.',
        score: 3,
      },
    ],
  },
  {
    id: 6,
    category: 'Personal Information',
    title: 'What is your age group?',
    subtitle: 'Age helps provide context for a health screening.',
    options: [
      {
        label: 'Under 18',
        desc: 'Younger than 18 years.',
        score: 0,
      },
      {
        label: '18–39 Years',
        desc: 'Between 18 and 39 years.',
        score: 0,
      },
      {
        label: '40 Years or Older',
        desc: '40 years or above.',
        score: 0,
      },
    ],
  },
  {
    id: 7,
    category: 'Personal Information',
    title: 'How do you describe your sex?',
    subtitle: 'This information may help a clinician interpret your symptoms.',
    options: [
      {
        label: 'Male',
        desc: 'Male.',
        score: 0,
      },
      {
        label: 'Female',
        desc: 'Female.',
        score: 0,
      },
      {
        label: 'Prefer Not to Say',
        desc: 'Skip this information.',
        score: 0,
      },
    ],
  },
  {
    id: 10,
    category: 'Medical History',
    title: 'Have you been diagnosed with any thyroid disorder?',
    subtitle: 'Select your known thyroid condition, if any.',
    options: [
      {
        label: 'Hypothyroidism',
        desc: 'Underactive thyroid.',
        score: 0,
      },
      {
        label: 'Hyperthyroidism',
        desc: 'Overactive thyroid.',
        score: 0,
      },
      {
        label: 'None',
        desc: 'I have not been diagnosed with a thyroid disorder.',
        score: 0,
      },
    ],
  },
];
