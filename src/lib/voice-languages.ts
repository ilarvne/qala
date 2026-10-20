import languages from "../../data/voice-languages.json";

export type VoiceLanguage = "en" | "ru" | "kk" | "de" | "fr" | "es" | "zh" | "ar" | "tr" | "hi" | "ja" | "ko" | "uk" | "it" | "ky" | "az";
export const voiceLanguages = languages as Array<{ code: VoiceLanguage; name: string; first_message: string }>;
export const isVoiceLanguage = (value: string): value is VoiceLanguage => voiceLanguages.some(language => language.code === value);
