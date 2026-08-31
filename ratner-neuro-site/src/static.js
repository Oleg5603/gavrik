const questions = [
  { id: 'urgent', title: 'Есть ли сейчас хотя бы один тревожный признак?', hint: 'Судороги, потеря сознания, внезапная слабость в руке или ноге, затруднение дыхания, резкое ухудшение состояния.', redFlag: true },
  { id: 'regression', title: 'Ребёнок утратил навык, которым раньше уверенно владел?', hint: 'Например, перестал удерживать голову, сидеть, ходить или говорить так, как раньше.' },
  { id: 'movement', title: 'Вы замечаете стойкую асимметрию движений или необычную скованность?', hint: 'Одна сторона тела двигается заметно меньше, движения регулярно ограничены или болезненны.' },
  { id: 'development', title: 'Есть опасения по поводу развития ребёнка?', hint: 'Сравнивать лучше не с другими детьми, а с динамикой самого ребёнка и рекомендациями педиатра.' },
];

function evaluateAnswers(values) {
  if (values.urgent) return 'emergency';
  if (values.regression) return 'soon';
  if (values.movement || values.development) return 'planned';
  return 'observe';
}

const resultCopy = {
  emergency: ['danger', 'Нужна экстренная медицинская помощь', 'Не продолжайте опрос. Позвоните 112 или 103. Если ребёнку трудно дышать, он без сознания или у него судороги — следуйте указаниям диспетчера.'],
  soon: ['warning', 'Обратитесь к врачу в ближайшее время', 'Утрата ранее приобретённого навыка требует очной оценки. Свяжитесь с педиатром или детским неврологом сегодня либо в срок, который подскажет медицинский специалист.'],
  planned: ['calm', 'Запланируйте консультацию', 'Обсудите наблюдения с педиатром. Запишите, когда появились изменения, как часто они повторяются и что на них влияет. Не проверяйте рефлексы самостоятельно.'],
  observe: ['good', 'Срочных сигналов по ответам не выявлено', 'Продолжайте обычное наблюдение и плановые осмотры. Этот результат не исключает заболевание: если вас что-то беспокоит, обсудите это с педиатром.'],
};

const root = document.querySelector('#questionnaire');
let step = 0;
let answers = {};

function renderQuestion() {
  const question = questions[step];
  const progress = ((step + 1) / questions.length) * 100;
  root.innerHTML = `<div class="question-card"><div class="progress-row"><span>Вопрос ${step + 1} из ${questions.length}</span><span>${Math.round(progress)}%</span></div><div class="progress"><span style="width:${progress}%"></span></div><h3>${question.title}</h3><p>${question.hint}</p><div class="answer-row"><button class="primary" data-answer="yes">Да</button><button class="secondary" data-answer="no">Нет</button></div><p class="privacy-note">Ответы обрабатываются только в вашем браузере и никуда не отправляются.</p></div>`;
  root.querySelectorAll('[data-answer]').forEach((button) => button.addEventListener('click', () => answer(button.dataset.answer === 'yes')));
}

function answer(value) {
  const question = questions[step];
  answers[question.id] = value;
  if (question.redFlag && value) return renderResult('emergency');
  if (step === questions.length - 1) return renderResult(evaluateAnswers(answers));
  step += 1;
  renderQuestion();
}

function renderResult(result) {
  const [tone, title, text] = resultCopy[result];
  root.innerHTML = `<div class="result ${tone}" role="status"><span class="result-kicker">Рекомендованный следующий шаг</span><h3>${title}</h3><p>${text}</p>${result === 'emergency' ? '<a class="primary" href="tel:112">Позвонить 112</a>' : ''}<button class="secondary" id="reset">Начать заново</button></div>`;
  root.querySelector('#reset').addEventListener('click', () => { step = 0; answers = {}; renderQuestion(); });
}

renderQuestion();
