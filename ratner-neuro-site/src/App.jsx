import { useState } from 'react';
import { questions, evaluateAnswers, RULES_STATUS } from './rules.js';

const resultCopy = {
  emergency: {
    tone: 'danger',
    title: 'Нужна экстренная медицинская помощь',
    text: 'Не продолжайте опрос. Позвоните 112 или 103. Если ребёнку трудно дышать, он без сознания или у него судороги — следуйте указаниям диспетчера.',
  },
  soon: {
    tone: 'warning',
    title: 'Обратитесь к врачу в ближайшее время',
    text: 'Утрата ранее приобретённого навыка требует очной оценки. Свяжитесь с педиатром или детским неврологом сегодня либо в срок, который подскажет медицинский специалист.',
  },
  planned: {
    tone: 'calm',
    title: 'Запланируйте консультацию',
    text: 'Обсудите наблюдения с педиатром. Запишите, когда появились изменения, как часто они повторяются и что на них влияет. Не проверяйте рефлексы самостоятельно.',
  },
  observe: {
    tone: 'good',
    title: 'Срочных сигналов по ответам не выявлено',
    text: 'Продолжайте обычное наблюдение и плановые осмотры. Этот результат не исключает заболевание: если вас что-то беспокоит, обсудите это с педиатром.',
  },
};

function Header() {
  return (
    <header className="header">
      <a className="brand" href="#top" aria-label="На главную">
        <span className="brand-mark">Н</span>
        <span>НейроНавигатор<small>информационный помощник</small></span>
      </a>
      <nav aria-label="Основная навигация">
        <a href="#about">О проекте</a>
        <a href="#warning">Тревожные признаки</a>
        <a className="nav-action" href="#check">Пройти проверку</a>
      </nav>
    </header>
  );
}

function Questionnaire() {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const question = questions[step];

  function answer(value) {
    const next = { ...answers, [question.id]: value };
    setAnswers(next);
    if (question.redFlag && value) {
      setResult('emergency');
    } else if (step === questions.length - 1) {
      setResult(evaluateAnswers(next));
    } else {
      setStep(step + 1);
    }
  }

  function reset() {
    setAnswers({});
    setStep(0);
    setResult(null);
  }

  if (result) {
    const copy = resultCopy[result];
    return (
      <div className={`result ${copy.tone}`} role="status">
        <span className="result-kicker">Рекомендованный следующий шаг</span>
        <h3>{copy.title}</h3>
        <p>{copy.text}</p>
        {result === 'emergency' && <a className="primary" href="tel:112">Позвонить 112</a>}
        <button className="secondary" type="button" onClick={reset}>Начать заново</button>
      </div>
    );
  }

  return (
    <div className="question-card">
      <div className="progress-row">
        <span>Вопрос {step + 1} из {questions.length}</span>
        <span>{Math.round(((step + 1) / questions.length) * 100)}%</span>
      </div>
      <div className="progress"><span style={{ width: `${((step + 1) / questions.length) * 100}%` }} /></div>
      <h3>{question.title}</h3>
      <p>{question.hint}</p>
      <div className="answer-row">
        <button className="primary" type="button" onClick={() => answer(true)}>Да</button>
        <button className="secondary" type="button" onClick={() => answer(false)}>Нет</button>
      </div>
      <p className="privacy-note">Ответы обрабатываются только в вашем браузере и никуда не отправляются.</p>
    </div>
  );
}

export default function App() {
  return (
    <div id="top">
      <Header />
      <main>
        <section className="hero">
          <div className="hero-copy">
            <span className="eyebrow">Спокойно разобраться в ситуации</span>
            <h1>Понятный маршрут, когда вы беспокоитесь о развитии ребёнка</h1>
            <p>Ответьте на несколько простых вопросов и узнайте, насколько срочно стоит обратиться за профессиональной помощью.</p>
            <div className="hero-actions">
              <a className="primary" href="#check">Начать проверку</a>
              <a className="text-link" href="#warning">Сначала увидеть тревожные признаки →</a>
            </div>
            <p className="safe-label">Без регистрации · Без сохранения данных · 2 минуты</p>
          </div>
          <div className="hero-visual" aria-hidden="true">
            <div className="orbit one" /><div className="orbit two" />
            <div className="figure"><span className="head" /><span className="body" /><i className="pulse p1" /><i className="pulse p2" /><i className="pulse p3" /></div>
          </div>
        </section>

        <section className="notice" aria-label="Важное ограничение">
          <strong>Важно:</strong> сервис не ставит диагноз, не определяет зону поражения и не назначает обследования. Он помогает подготовиться к разговору с врачом.
        </section>

        <section id="warning" className="section warning-section">
          <div><span className="eyebrow">Когда нельзя ждать</span><h2>Сразу звоните 112 или 103</h2></div>
          <div className="warning-grid">
            <article><b>01</b><h3>Судороги или потеря сознания</h3><p>Особенно если это произошло впервые или состояние не восстанавливается.</p></article>
            <article><b>02</b><h3>Внезапная слабость</h3><p>Ребёнок неожиданно перестал двигать рукой, ногой или появилась резкая асимметрия лица.</p></article>
            <article><b>03</b><h3>Нарушение дыхания</h3><p>Затруднённое дыхание, посинение губ или выраженная вялость требуют экстренной помощи.</p></article>
          </div>
        </section>

        <section id="check" className="section check-section">
          <div className="section-heading"><span className="eyebrow">Демо-проверка</span><h2>Определим следующий безопасный шаг</h2><p>Отвечайте только на то, что вы наблюдаете. Не выполняйте домашние неврологические тесты.</p></div>
          <Questionnaire />
        </section>

        <section id="about" className="section about-section">
          <div><span className="eyebrow">О проекте</span><h2>Информация вместо самодиагностики</h2></div>
          <div><p>Первая версия создана для проверки структуры и пользовательского сценария. Она не использует методические матрицы, не обрабатывает медицинские данные и не заменяет очную консультацию.</p><p className="draft">Статус правил: {RULES_STATUS}</p></div>
        </section>
      </main>
      <footer><span>НейроНавигатор · безопасный прототип</span><span>При угрозе жизни звоните 112</span></footer>
    </div>
  );
}
