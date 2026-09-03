'use client';

import React from 'react';
import { ClipboardCheck, Edit3 } from 'lucide-react';
import { EstimatorFormData } from '@/types/estimator';
import { formatNumber } from '@/lib/utils';

interface Step4ReviewProps {
  formData: EstimatorFormData;
  goToStep: (step: number) => void;
  locale: string;
  dict: any;
}

export function Step4Review({ formData, goToStep, locale, dict }: Step4ReviewProps) {
  const d = dict.estimation;

  const reviewSections = [
    {
      title: d.step1,
      stepNumber: 1,
      items: [
        { label: d.cityField, value: formData.ville },
        { label: d.districtField, value: formData.quartier || d.notSpecified },
      ],
    },
    {
      title: d.step2,
      stepNumber: 2,
      items: [
        { label: d.typeField, value: locale === 'ar' ? 'شقة' : 'Appartement' },
      ],
    },
    {
      title: d.step3,
      stepNumber: 3,
      items: [
        { label: d.surfaceField, value: `${formatNumber(formData.surface, locale)} m²` },
        { label: d.roomsField, value: formData.pieces ? formatNumber(formData.pieces, locale) : d.notSpecified },
        { label: d.bedroomsField, value: formData.chambres ? formatNumber(formData.chambres, locale) : d.notSpecified },
        { label: d.bathroomsField, value: formData.salles_bain ? formatNumber(formData.salles_bain, locale) : d.notSpecified },
        { label: d.standingField, value: formData.haut_standing ? d.yes : d.no },
      ],
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/60 dark:border-white/5 mb-6">
        <ClipboardCheck className="w-5 h-5 text-brand-blue dark:text-blue-400 shrink-0" />
        <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
          {d.reviewNotice}
        </p>
      </div>

      <div className="space-y-4">
        {reviewSections.map((sec) => (
          <div
            key={sec.stepNumber}
            className="p-5 rounded-2xl bg-white dark:bg-brand-navy-surface border border-slate-200/80 dark:border-white/10"
          >
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-100 dark:border-white/5">
              <span className="text-xs font-bold uppercase tracking-wider text-brand-blue dark:text-blue-400">
                {sec.title}
              </span>
              <button
                type="button"
                onClick={() => goToStep(sec.stepNumber)}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-brand-blue dark:hover:text-blue-400 transition-colors"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>{dict.common.edit}</span>
              </button>
            </div>

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2.5">
              {sec.items.map((item, i) => (
                <div key={i} className="flex justify-between sm:justify-start sm:gap-4 text-xs">
                  <dt className="text-slate-500 dark:text-slate-400 font-medium min-w-[100px]">
                    {item.label} :
                  </dt>
                  <dd className="text-slate-900 dark:text-white font-semibold">
                    {item.value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </div>
  );
}
