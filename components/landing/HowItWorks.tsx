'use client';

import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Layers, Cpu, TrendingUp, CheckCircle2, ShieldCheck, Sparkles, Building2, BarChart3 } from 'lucide-react';
import { isRTL } from '@/lib/i18n/config';

interface HowItWorksProps {
  locale: string;
  dict: any;
}

export function HowItWorks({ locale, dict }: HowItWorksProps) {
  const [activeStep, setActiveStep] = useState(0);
  const rtl = isRTL(locale);

  const steps = [
    {
      num: dict.howItWorks.step1Number,
      title: dict.howItWorks.step1Title,
      desc: dict.howItWorks.step1Desc,
      icon: <Layers className="w-5 h-5 text-brand-blue dark:text-blue-400" />,
      detail: locale === 'ar' ? 'المعايير الهندسية' : 'Paramètres intrinsèques',
      badge: locale === 'ar' ? 'المرحلة الأولى' : 'Étape Initiale',
    },
    {
      num: dict.howItWorks.step2Number,
      title: dict.howItWorks.step2Title,
      desc: dict.howItWorks.step2Desc,
      icon: <Cpu className="w-5 h-5 text-brand-blue dark:text-blue-400" />,
      detail: locale === 'ar' ? 'المطابقة الإحصائية' : 'Rapprochement statistique',
      badge: locale === 'ar' ? 'المرحلة التحليلية' : 'Calibrage ML',
    },
    {
      num: dict.howItWorks.step3Number,
      title: dict.howItWorks.step3Title,
      desc: dict.howItWorks.step3Desc,
      icon: <TrendingUp className="w-5 h-5 text-brand-blue dark:text-blue-400" />,
      detail: locale === 'ar' ? 'القيمة والمجال' : 'Valeur & Dispersion',
      badge: locale === 'ar' ? 'مخرجات النموذج' : 'Restitution Finale',
    },
  ];

  const containerRef = useRef<HTMLDivElement>(null);

  // IntersectionObserver to sync sticky visual with scrolling story steps
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const stepElements = container.querySelectorAll('[data-step-index]');
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const index = Number(entry.target.getAttribute('data-step-index'));
            if (!isNaN(index)) {
              setActiveStep(index);
            }
          }
        });
      },
      {
        rootMargin: '-30% 0px -40% 0px',
        threshold: 0.2,
      }
    );

    stepElements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);

  return (
    <section
      id="demarche"
      className="min-h-auto lg:min-h-[100svh] py-16 sm:py-20 lg:py-12 scroll-mt-24 lg:scroll-mt-28 bg-slate-50/70 dark:bg-brand-navy-deep/80 transition-colors border-t border-slate-200/80 dark:border-white/5 relative overflow-hidden flex flex-col justify-center"
    >
      {/* Background Architectural Grid Accents */}
      <div className="absolute inset-0 pointer-events-none opacity-30 dark:opacity-15">
        <div className="max-w-7xl mx-auto h-full border-x border-slate-200/60 dark:border-white/5" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 w-full">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-8% 0px' }}
          transition={{ duration: 0.5 }}
          className="max-w-3xl mb-8 lg:mb-10"
        >
          <span className="text-xs font-bold uppercase tracking-wider text-brand-blue dark:text-blue-400 mb-2 block">
            {dict.howItWorks.badge}
          </span>
          <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-slate-900 dark:text-white leading-[1.15]">
            {dict.howItWorks.title}
          </h2>
          <p className="mt-2.5 text-sm sm:text-base text-slate-600 dark:text-slate-300 leading-relaxed">
            {dict.howItWorks.subtitle}
          </p>
        </motion.div>

        {/* Sticky Storytelling Layout on Desktop */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start">
          {/* Left / Right Sticky Visual Stage Canvas */}
          <div className="lg:col-span-5 hidden lg:block sticky top-28 sm:top-32">
            <div className="relative rounded-2xl p-6 backdrop-blur-xl bg-white/85 dark:bg-[#0c1322]/85 border border-slate-200/90 dark:border-white/10 shadow-[0_12px_40px_-8px_rgba(15,23,42,0.08)] dark:shadow-[0_16px_48px_-8px_rgba(0,0,0,0.6)] overflow-hidden min-h-[380px] lg:min-h-[400px] flex flex-col justify-between">
              {/* Background Ambient Glow */}
              <div className="absolute -top-24 -right-24 w-60 h-60 bg-blue-500/10 dark:bg-blue-500/20 rounded-full blur-3xl pointer-events-none" />

              {/* Header of Sticky Visual */}
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-white/5 pb-4">
                <div className="flex items-center gap-2.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-brand-blue animate-pulse" />
                  <span className="text-xs font-mono font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    {locale === 'ar' ? 'مختبر التقييم الرقمي' : 'Laboratoire d\'Évaluation'}
                  </span>
                </div>
                <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-brand-blue/10 text-brand-blue dark:text-blue-300 border border-brand-blue/20">
                  {steps[activeStep].badge}
                </span>
              </div>

              {/* Dynamic Interactive Visuals for Each Step */}
              <div className="my-auto py-6">
                <AnimatePresence mode="wait">
                  {activeStep === 0 && (
                    <motion.div
                      key="step-0-visual"
                      initial={{ opacity: 0, scale: 0.96, y: 8 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.96, y: -8 }}
                      transition={{ duration: 0.35 }}
                      className="space-y-4"
                    >
                      <div className="flex items-center justify-between text-xs text-slate-500">
                        <span className="font-medium flex items-center gap-1.5 text-slate-900 dark:text-white font-semibold">
                          <Building2 className="w-4 h-4 text-brand-blue" />
                          {locale === 'ar' ? 'مخطط البيانات الأساسية' : 'Schéma des Attributs'}
                        </span>
                        <span className="font-mono text-[11px] text-emerald-600 dark:text-emerald-400 font-bold">
                          ✓ Vérifié
                        </span>
                      </div>

                      {/* Schematic Grid of Parameters */}
                      <div className="grid grid-cols-2 gap-2.5 text-xs">
                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-200/60 dark:border-white/5">
                          <span className="text-[10px] text-slate-400 block mb-0.5">Typologie</span>
                          <span className="font-bold text-slate-900 dark:text-white">Appartement</span>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-200/60 dark:border-white/5">
                          <span className="text-[10px] text-slate-400 block mb-0.5">Surface brute</span>
                          <span className="font-bold text-slate-900 dark:text-white">95 m² habitables</span>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-200/60 dark:border-white/5">
                          <span className="text-[10px] text-slate-400 block mb-0.5">Distribution</span>
                          <span className="font-bold text-slate-900 dark:text-white">3 ch. · 2 sdb</span>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-200/60 dark:border-white/5">
                          <span className="text-[10px] text-slate-400 block mb-0.5">Finition</span>
                          <span className="font-bold text-slate-900 dark:text-white">Haut standing</span>
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-blue-50/70 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-900/40 text-[11px] text-blue-800 dark:text-blue-300">
                        {locale === 'ar'
                          ? 'استبعاد التخمينات الذاتية وتحديد الهيكل الهندسي الدقيق للعقار.'
                          : 'Structuration univoque des vecteurs caractéristiques sans bruit descriptif.'}
                      </div>
                    </motion.div>
                  )}

                  {activeStep === 1 && (
                    <motion.div
                      key="step-1-visual"
                      initial={{ opacity: 0, scale: 0.96, y: 8 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.96, y: -8 }}
                      transition={{ duration: 0.35 }}
                      className="space-y-4"
                    >
                      <div className="flex items-center justify-between text-xs text-slate-500">
                        <span className="font-medium flex items-center gap-1.5 text-slate-900 dark:text-white font-semibold">
                          <Cpu className="w-4 h-4 text-brand-blue" />
                          {locale === 'ar' ? 'محرك المطابقة الإحصائية' : 'Moteur de Régression Sectorielle'}
                        </span>
                        <span className="font-mono text-[11px] text-brand-blue dark:text-blue-400 font-bold">
                          Processing...
                        </span>
                      </div>

                      {/* Neural / Regression Match Bars */}
                      <div className="space-y-2.5">
                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-200/60 dark:border-white/5">
                          <div className="flex justify-between text-[11px] mb-1.5">
                            <span className="text-slate-600 dark:text-slate-300 font-medium">
                              {locale === 'ar' ? 'تنقية البيانات من القيم الشاذة' : 'Filtrage outliers & doublons'}
                            </span>
                            <span className="font-mono text-emerald-600 font-bold">100%</span>
                          </div>
                          <div className="h-1.5 w-full bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: '100%' }}
                              transition={{ duration: 0.6 }}
                              className="h-full bg-emerald-500 rounded-full"
                            />
                          </div>
                        </div>

                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-200/60 dark:border-white/5">
                          <div className="flex justify-between text-[11px] mb-1.5">
                            <span className="text-slate-600 dark:text-slate-300 font-medium">
                              {locale === 'ar' ? 'تطابق السلسلة الزمنية للمدينة' : 'Corpus géographique audité'}
                            </span>
                            <span className="font-mono text-brand-blue dark:text-blue-400 font-bold">Actif</span>
                          </div>
                          <div className="h-1.5 w-full bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: '92%' }}
                              transition={{ duration: 0.6, delay: 0.1 }}
                              className="h-full bg-brand-blue rounded-full"
                            />
                          </div>
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-slate-100/80 dark:bg-slate-800/50 border border-slate-200/60 dark:border-white/5 text-[11px] text-slate-600 dark:text-slate-300">
                        {locale === 'ar'
                          ? 'المطابقة الحصرية مع العقارات المماثلة الفعلية في نفس المدينة والحي.'
                          : 'Aucune extrapolation hors territoire. Calibrage strict sur le corpus audité.'}
                      </div>
                    </motion.div>
                  )}

                  {activeStep === 2 && (
                    <motion.div
                      key="step-2-visual"
                      initial={{ opacity: 0, scale: 0.96, y: 8 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.96, y: -8 }}
                      transition={{ duration: 0.35 }}
                      className="space-y-4"
                    >
                      <div className="flex items-center justify-between text-xs text-slate-500">
                        <span className="font-medium flex items-center gap-1.5 text-slate-900 dark:text-white font-semibold">
                          <BarChart3 className="w-4 h-4 text-brand-blue" />
                          {locale === 'ar' ? 'المؤشرات والفاصل الرياضي' : 'Restitution d\'Encadrement'}
                        </span>
                        <span className="font-mono text-[11px] text-blue-600 dark:text-blue-400 font-bold">
                          MAD
                        </span>
                      </div>

                      {/* Valuation Gauge Card */}
                      <div className="p-4 rounded-2xl bg-gradient-to-br from-brand-blue/10 via-transparent to-blue-500/5 border border-brand-blue/20 text-center space-y-2">
                        <span className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 block font-semibold">
                          {locale === 'ar' ? 'القيمة الإرشادية المحسوبة' : 'Estimation Indicative du Modèle'}
                        </span>
                        <div className="text-2xl sm:text-3xl font-black text-brand-navy dark:text-white">
                          1 250 000 <span className="text-base font-bold text-brand-blue">MAD</span>
                        </div>
                        <div className="pt-2 border-t border-slate-200/60 dark:border-white/10 flex justify-around text-xs">
                          <div>
                            <span className="text-[10px] text-slate-400 block">Fourchette basse</span>
                            <span className="font-bold text-slate-700 dark:text-slate-200">1 190 000 MAD</span>
                          </div>
                          <div>
                            <span className="text-[10px] text-slate-400 block">Fourchette haute</span>
                            <span className="font-bold text-slate-700 dark:text-slate-200">1 320 000 MAD</span>
                          </div>
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-emerald-50/70 dark:bg-emerald-950/30 border border-emerald-200/60 dark:border-emerald-900/40 text-[11px] text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                        <span>
                          {locale === 'ar'
                            ? 'إظهار النتائج بناءً على عقد البيانات الرسمي فقط.'
                            : 'Encadrement basé uniquement sur les retours réels du moteur d\'inférence.'}
                        </span>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Visual Step Progress Dots */}
              <div className="border-t border-slate-100 dark:border-white/5 pt-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {steps.map((_, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => setActiveStep(i)}
                      className={`h-2 rounded-full transition-all duration-300 ${
                        activeStep === i
                          ? 'w-7 bg-brand-blue shadow-sm'
                          : 'w-2 bg-slate-200 dark:bg-slate-700 hover:bg-slate-300'
                      }`}
                      aria-label={`Étape ${i + 1}`}
                    />
                  ))}
                </div>
                <span className="text-xs font-mono font-medium text-slate-400">
                  0{activeStep + 1} / 03
                </span>
              </div>
            </div>
          </div>

          {/* Scrolling Steps Narrative Column */}
          <div ref={containerRef} className="lg:col-span-7 space-y-6 sm:space-y-8">
            {steps.map((step, idx) => {
              const isActive = activeStep === idx;
              return (
                <div
                  key={step.num}
                  data-step-index={idx}
                  className={`relative p-6 sm:p-7 rounded-2xl transition-all duration-300 ${
                    isActive
                      ? 'bg-white dark:bg-brand-navy-surface border-2 border-brand-blue/50 dark:border-blue-400/50 shadow-xl shadow-slate-900/5 dark:shadow-black/40 scale-[1.01]'
                      : 'bg-white/70 dark:bg-brand-navy-surface/50 border border-slate-200/80 dark:border-white/5 shadow-xs opacity-75 hover:opacity-100'
                  }`}
                >
                  <div className="flex items-center justify-between mb-4">
                    <span
                      className={`text-2xl sm:text-3xl font-black tracking-wider transition-colors ${
                        isActive ? 'text-brand-blue dark:text-blue-400' : 'text-slate-300 dark:text-slate-700'
                      }`}
                    >
                      {step.num}
                    </span>
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                        isActive
                          ? 'bg-brand-blue/10 dark:bg-blue-500/20 text-brand-blue dark:text-blue-400 border border-brand-blue/20'
                          : 'bg-slate-50 dark:bg-slate-800 text-slate-400'
                      }`}
                    >
                      {step.icon}
                    </div>
                  </div>

                  <span className="text-[11px] font-bold uppercase tracking-wider text-brand-blue dark:text-blue-400 block mb-1">
                    {step.detail}
                  </span>
                  <h3 className="text-lg sm:text-xl font-bold text-slate-900 dark:text-white mb-2.5">
                    {step.title}
                  </h3>
                  <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                    {step.desc}
                  </p>

                  {/* Inline visual fallback for mobile only */}
                  <div className="lg:hidden mt-6 pt-4 border-t border-slate-100 dark:border-white/5">
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                      <Sparkles className="w-3.5 h-3.5 text-brand-blue" />
                      {step.badge}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
