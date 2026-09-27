/* Local catalogs only. Translate app-owned messages, never documents or input. */
const i18n = (() => {
  const catalog = window.LoxmitEnglish;
  const browserLanguage = () => (navigator.languages?.[0] || navigator.language || 'en').toLowerCase().startsWith('ja') ? 'ja' : 'en';
  let preference = 'auto', language = browserLanguage();
  const attributes = ['title', 'placeholder', 'aria-label', 'alt'];
  const patterns = Object.entries(catalog).filter(([key]) => /\{\d+\}/.test(key)).map(([key, value]) => {
    const escaped = key.split(/(\{\d+\})/).map(part => /^\{\d+\}$/.test(part) ? '([\\s\\S]*?)' : part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('');
    return [new RegExp('^' + escaped + '$'), value, key];
  });
  function format(template, values) { return template.replace(/\{(\d+)\}/g, (match, index) => index < values.length ? String(values[index]) : match); }
  function translate(source, ...values) {
    if (Array.isArray(source)) source = source.reduce((result, part, index) => result + (index ? '{' + (index - 1) + '}' : '') + part, '');
    return format(language === 'en' && Object.hasOwn(catalog, source) ? catalog[source] : source, values);
  }
  // Legacy saved events keep their original text. Localize only designated
  // message fields at the presentation boundary; raw tool logs stay verbatim.
  function message(source, depth = 0) {
    if (typeof source !== 'string' || language === 'ja') return source;
    if (Object.hasOwn(catalog, source)) return catalog[source];
    if (depth > 4) return source;
    for (const ending of [' 保存地点から再開できます。', ' 保存地点がないため、再開時は候補の最初から探索します。']) {
      if (source.endsWith(ending)) return message(source.slice(0, -ending.length), depth + 1) + translate(ending);
    }
    if (source.length <= 8192) for (const [pattern, target, key] of patterns) {
      const match = source.match(pattern);
      if (match) {
        const values = match.slice(1);
        if (['段階 {0}/{1}: {2}', '{0} / 全体{1}文字', '開封エラー: {0}', '書き出しエラー: {0}', '探索の準備に失敗しました: {0}', '処理に失敗しました: {0}', 'ファイルを読み取れませんでした: {0}'].includes(key)) {
          const index = key.startsWith('段階') ? 2 : 0;
          values[index] = message(values[index], depth + 1);
        }
        return format(target, values);
      }
    }
    return source;
  }
  function apply() {
    document.documentElement.lang = language;
    for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = translate(node.dataset.i18n);
    for (const attr of attributes) for (const node of document.querySelectorAll('[data-i18n-' + attr + ']')) node.setAttribute(attr, translate(node.getAttribute('data-i18n-' + attr)));
    const selector = document.getElementById('language');
    if (selector) selector.value = preference;
  }
  function use(value) {
    preference = ['ja', 'en'].includes(value) ? value : 'auto';
    language = preference === 'auto' ? browserLanguage() : preference;
    apply();
    document.dispatchEvent(new Event('loxmit-language'));
  }
  async function set(value) {
    if (!['auto', 'ja', 'en'].includes(value)) throw Error('Invalid language');
    const response = await fetch('/api/language', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Loxmit': '1'}, body: JSON.stringify({language: value})});
    if (!response.ok) throw Error(translate('言語設定を保存できませんでした。'));
    use(value);
  }
  const ready = fetch('/api/language').then(response => response.ok ? response.json() : {}).then(result => use(result.language)).catch(() => use('auto'));
  return {t: translate, message, set, apply, ready, get language() { return language; }, get preference() { return preference; }, get locale() { return language === 'ja' ? 'ja-JP' : 'en-US'; }};
})();
const t = i18n.t;
const localized = values => new Proxy(values, {get: (target, key) => typeof target[key] === 'string' ? t(target[key]) : target[key]});
