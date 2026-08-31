export const RULES_STATUS = 'draft — требуется утверждение врачом';

export const questions = [
  {
    id: 'urgent',
    title: 'Есть ли сейчас хотя бы один тревожный признак?',
    hint: 'Судороги, потеря сознания, внезапная слабость в руке или ноге, затруднение дыхания, резкое ухудшение состояния.',
    redFlag: true,
  },
  {
    id: 'regression',
    title: 'Ребёнок утратил навык, которым раньше уверенно владел?',
    hint: 'Например, перестал удерживать голову, сидеть, ходить или говорить так, как раньше.',
  },
  {
    id: 'movement',
    title: 'Вы замечаете стойкую асимметрию движений или необычную скованность?',
    hint: 'Одна сторона тела двигается заметно меньше, движения регулярно ограничены или болезненны.',
  },
  {
    id: 'development',
    title: 'Есть опасения по поводу развития ребёнка?',
    hint: 'Сравнивать лучше не с другими детьми, а с динамикой самого ребёнка и рекомендациями педиатра.',
  },
];

export function evaluateAnswers(answers) {
  if (answers.urgent === true) return 'emergency';
  if (answers.regression === true) return 'soon';
  if (answers.movement === true || answers.development === true) return 'planned';
  return 'observe';
}
