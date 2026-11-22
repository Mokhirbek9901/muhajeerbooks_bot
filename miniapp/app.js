'use strict';

const telegram = window.Telegram?.WebApp;
const view = document.getElementById('view');
const tabs = document.getElementById('tabs');
const toast = document.getElementById('toast');
const number = new Intl.NumberFormat('en-US');
const won = amount => '₩' + number.format(amount || 0);
const POSTAGE = 4000;
const FREE_POSTAGE_BOOKS = 4;
const languageKey = 'muhajeer-mini-interface-language';
const bookLanguageKey = 'muhajeer-mini-book-language';
const languages = [['uz', 'O‘zbekcha'], ['en', 'English'], ['ru', 'Русский']];
let interfaceLanguage = localStorage.getItem(languageKey) || '';
let bookLanguage = localStorage.getItem(bookLanguageKey) || interfaceLanguage || 'uz';
const copy = {
  en: {
    'Kitoblar': 'Catalog', 'Savatcha': 'Cart', 'Buyurtmalar': 'Orders', 'Profil': 'Profile',
    'Kitob qidirish': 'Search books', 'Qidirish': 'Search', 'Yangilash': 'Refresh',
    'Hammasi': 'All', 'Kitob topilmadi.': 'No books found.',
    'Barcha kitoblar': 'All books', 'Kategoriya': 'Category', 'Saralash': 'Sort',
    'Yangi qo‘shilgan': 'Newest', 'Narxi arzon': 'Lowest price', 'Narxi qimmat': 'Highest price',
    'Nom bo‘yicha': 'Title A–Z', 'ta kitob': 'books', 'Rasmlar': 'Photos',
    'Kitoblar yuklanmoqda…': 'Loading books…', 'Qayta urinish': 'Try again',
    'Savatchaga qo‘shish': 'Add to cart', 'Savatchaga qo‘shildi': 'Added to cart',
    'Qoldiqdan ortiq miqdor tanlandi.': 'The selected quantity exceeds available stock.',
    'Savatchaga 50 turdagi kitob qo‘shish mumkin.': 'The cart can contain up to 50 book titles.',
    'Savatcha bo‘sh.': 'Your cart is empty.', 'Kitoblarni ko‘rish': 'Browse books',
    'Kitoblar jami': 'Books subtotal', 'Pochta': 'Delivery', 'Olib ketish': 'Pickup',
    'Bepul': 'Free', 'Jami': 'Total', 'Buyurtma berish': 'Checkout',
    'Ism': 'Name', 'Telefon raqami': 'Phone number', 'Yetkazish': 'Delivery method',
    'Pochta orqali': 'Delivery', 'Gyeongsan’da olib ketish': 'Pick up in Gyeongsan',
    'Manzil': 'Address', 'Jami summani ko‘rish': 'Review total', 'Buyurtma': 'Order',
    'Buyurtma qabul qilinganda va jo‘natilganda Telegramdan xabar oling.': 'Receive Telegram updates when your order is accepted and shipped.',
    'Telegram xabarlarini yoqish': 'Enable Telegram notifications',
    'Telegram xabarlari yoqildi.': 'Telegram notifications are enabled.',
    'Buyurtma holatini «Buyurtmalar» bo‘limida ko‘rishingiz mumkin.': 'You can track the order in Orders.',
    'To‘lov': 'Payment', 'Yetkazish': 'Delivery',
    'To‘lov cheki': 'Payment receipt', 'Chekni yuborish': 'Send receipt',
    'Summani qayta tekshirish': 'Review total again', 'Hisob raqamini nusxalash': 'Copy bank account',
    'Hisob raqami nusxalandi': 'Bank account copied', 'Ma’lumotlar': 'Details',
    'Qabul qilindi': 'Accepted', 'Tayyorlandi': 'Prepared', 'Jo‘natildi': 'Shipped',
    'Bekor qilindi': 'Cancelled', 'Tekshirilmoqda': 'Under review', 'Kitob': 'Book',
    'Buyurtma yuborildi': 'Order submitted', 'Buyurtmalarim': 'My orders',
    'Yuklanmoqda…': 'Loading…', 'Yana buyurtmalar': 'More orders',
    'Mini App orqali berilgan buyurtmalar shu yerda ko‘rinadi.': 'Orders placed through the Mini App appear here.',
    'Tilni tanlang': 'Choose your language', 'Davom etish': 'Continue',
    'Ilova tili': 'App language', 'Saqlash': 'Save', 'Kitob tili': 'Book language',
  },
  ru: {
    'Kitoblar': 'Каталог', 'Savatcha': 'Корзина', 'Buyurtmalar': 'Заказы', 'Profil': 'Профиль',
    'Kitob qidirish': 'Поиск книг', 'Qidirish': 'Найти', 'Yangilash': 'Обновить',
    'Hammasi': 'Все', 'Kitob topilmadi.': 'Книги не найдены.',
    'Barcha kitoblar': 'Все книги', 'Kategoriya': 'Категория', 'Saralash': 'Сортировка',
    'Yangi qo‘shilgan': 'Сначала новые', 'Narxi arzon': 'Сначала дешевле', 'Narxi qimmat': 'Сначала дороже',
    'Nom bo‘yicha': 'По названию', 'ta kitob': 'книг', 'Rasmlar': 'Фотографии',
    'Kitoblar yuklanmoqda…': 'Загрузка книг…', 'Qayta urinish': 'Повторить',
    'Savatchaga qo‘shish': 'Добавить в корзину', 'Savatchaga qo‘shildi': 'Добавлено в корзину',
    'Qoldiqdan ortiq miqdor tanlandi.': 'Выбранное количество превышает остаток.',
    'Savatchaga 50 turdagi kitob qo‘shish mumkin.': 'В корзину можно добавить до 50 наименований.',
    'Savatcha bo‘sh.': 'Корзина пуста.', 'Kitoblarni ko‘rish': 'Перейти к книгам',
    'Kitoblar jami': 'Стоимость книг', 'Pochta': 'Доставка', 'Olib ketish': 'Самовывоз',
    'Bepul': 'Бесплатно', 'Jami': 'Итого', 'Buyurtma berish': 'Оформить заказ',
    'Ism': 'Имя', 'Telefon raqami': 'Номер телефона', 'Yetkazish': 'Способ доставки',
    'Pochta orqali': 'Доставка', 'Gyeongsan’da olib ketish': 'Самовывоз в Кёнсане',
    'Manzil': 'Адрес', 'Jami summani ko‘rish': 'Проверить сумму', 'Buyurtma': 'Заказ',
    'Buyurtma qabul qilinganda va jo‘natilganda Telegramdan xabar oling.': 'Получайте уведомления в Telegram о принятии и отправке заказа.',
    'Telegram xabarlarini yoqish': 'Включить уведомления Telegram',
    'Telegram xabarlari yoqildi.': 'Уведомления Telegram включены.',
    'Buyurtma holatini «Buyurtmalar» bo‘limida ko‘rishingiz mumkin.': 'Статус заказа доступен в разделе «Заказы».',
    'To‘lov': 'Оплата', 'Yetkazish': 'Доставка',
    'To‘lov cheki': 'Квитанция об оплате', 'Chekni yuborish': 'Отправить квитанцию',
    'Summani qayta tekshirish': 'Проверить сумму ещё раз', 'Hisob raqamini nusxalash': 'Скопировать номер счёта',
    'Hisob raqami nusxalandi': 'Номер счёта скопирован', 'Ma’lumotlar': 'Данные',
    'Qabul qilindi': 'Принят', 'Tayyorlandi': 'Подготовлен', 'Jo‘natildi': 'Отправлен',
    'Bekor qilindi': 'Отменён', 'Tekshirilmoqda': 'На проверке', 'Kitob': 'Книга',
    'Buyurtma yuborildi': 'Заказ отправлен', 'Buyurtmalarim': 'Мои заказы',
    'Yuklanmoqda…': 'Загрузка…', 'Yana buyurtmalar': 'Показать ещё',
    'Mini App orqali berilgan buyurtmalar shu yerda ko‘rinadi.': 'Здесь отображаются заказы из мини-приложения.',
    'Tilni tanlang': 'Выберите язык', 'Davom etish': 'Продолжить',
    'Ilova tili': 'Язык приложения', 'Saqlash': 'Сохранить', 'Kitob tili': 'Язык книг',
  },
};
const t = value => copy[interfaceLanguage]?.[value] || value;
const FREE_POSTAGE_TEXT = () => interfaceLanguage === 'ru'
  ? 'Бесплатная доставка при заказе от 4 книг.'
  : interfaceLanguage === 'en' ? 'Free delivery on orders of 4 or more books.'
  : '4 ta kitobdan boshlab pochta bepul.';
const tabNames = () => [['books', t('Kitoblar')], ['cart', t('Savatcha')],
  ['orders', t('Buyurtmalar')], ['profile', t('Profil')]];
const storageKey = 'muhajeer-mini-cart-' + (telegram?.initDataUnsafe?.user?.id || 'browser');
const persisted = readCart();
let cart = persisted.cart;
let draftId = persisted.draftId;
let current = 'books';
let catalog = {books: [], search: '', loadedAt: 0, category: '', sort: 'new'};
let searchText = '';
let pending = false;
let navigation = 0;
let toastTimer;
let messageAccess = Boolean(telegram?.initDataUnsafe?.user?.allows_write_to_pm);

function element(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value !== false && value !== undefined && value !== null) {
      node.setAttribute(key, value === true ? '' : value);
    }
  }
  node.append(...children.flat().filter(child => child !== null && child !== undefined)
    .map(child => typeof child === 'string' ? t(child) : child));
  return node;
}

function button(label, handler, kind = 'outline', attrs = {}) {
  return element('button', {type: 'button', class: kind, onclick: handler, ...attrs}, label);
}

function small(text, name = 'muted') {
  return element('p', {class: name}, text);
}

function stack(...children) {
  return element('section', {class: 'stack'}, ...children);
}

function glyph(name) {
  return element('span', {class: 'glyph glyph-' + name, 'aria-hidden': 'true'});
}

function stockBadge(book) {
  const count = book.stock;
  if (!Number.isInteger(count) || count < 0) return null;
  const state = count === 0 ? 'empty' : count <= 3 ? 'low' : 'available';
  const label = interfaceLanguage === 'ru' ? `В наличии: ${number.format(count)}`
    : interfaceLanguage === 'en' ? `In stock: ${number.format(count)}`
    : `Omborda ${number.format(count)} dona`;
  return element('span', {class: 'stock stock--' + state}, label);
}

function readCart() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (Array.isArray(saved?.cart)) return saved;
  } catch (_) { /* Storage may be unavailable in a WebView. */ }
  return {cart: [], draftId: ''};
}

function saveCart() {
  try {
    localStorage.setItem(storageKey, JSON.stringify({cart, draftId}));
  } catch (_) { /* The current session still keeps the cart. */ }
}

async function api(action, data = {}) {
  const response = await fetch('./api/' + action, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Telegram-Init-Data': telegram.initData},
    body: JSON.stringify(data),
    cache: 'no-store',
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const failure = new Error(result.error || 'Server javob bermadi. Qayta urinib ko‘ring.');
    failure.status = response.status;
    throw failure;
  }
  return result;
}

function showToast(message) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.hidden = false;
  toastTimer = setTimeout(() => { toast.hidden = true; }, 2100);
}

function display(component) {
  view.replaceChildren(component);
}

function changePage(page) {
  navigation++;
  current = page;
  window.scrollTo(0, 0);
  renderTabs();
  if (page === 'books') {
    if (Date.now() - catalog.loadedAt < 25000) renderCatalog();
    else loadCatalog(catalog.search);
  }
  if (page === 'cart') renderCart();
  if (page === 'orders') loadOrders(0);
  if (page === 'profile') renderLanguageSettings();
}

function renderTabs() {
  const count = cart.reduce((sum, line) => sum + line.quantity, 0);
  tabs.replaceChildren(...tabNames().map(([page, title]) => {
    const active = current === page || current === 'book' && page === 'books'
      || current === 'checkout' && page === 'cart';
    return button(
      element('span', {class: 'tab-content'}, glyph(page),
        element('span', {class: 'tab-label'}, title),
        page === 'cart' && count ? element('span', {class: 'cart-count'}, String(count)) : null),
      () => { if (!pending) changePage(page); },
      'tab', {'aria-current': active ? 'page' : null},
    );
  }));
}

function bookImages(book) {
  const values = [book.cover, ...(Array.isArray(book.images) ? book.images : [])];
  return [...new Set(values.filter(url => typeof url === 'string' && url.startsWith('https://')))];
}

function artwork(book, source = book.cover) {
  const placeholder = element('div', {class: 'cover placeholder', 'aria-hidden': true}, book.title);
  if (typeof source !== 'string' || !source.startsWith('https://')) return placeholder;
  const image = element('img', {
    class: 'cover', src: source, alt: book.title, loading: 'lazy', decoding: 'async',
    referrerpolicy: 'no-referrer', width: 240, height: 300,
  });
  image.addEventListener('error', () => image.replaceWith(placeholder), {once: true});
  return image;
}

function alterCart(book, change) {
  const found = cart.find(line => line.book.id === book.id);
  const count = (found?.quantity || 0) + change;
  if (change > 0 && (count > book.stock || count > 100)) {
    showToast('Qoldiqdan ortiq miqdor tanlandi.');
    return;
  }
  if (!found && cart.length >= 50) {
    showToast('Savatchaga 50 turdagi kitob qo‘shish mumkin.');
    return;
  }
  if (count <= 0) cart = cart.filter(line => line.book.id !== book.id);
  else if (found) Object.assign(found, {book, quantity: count});
  else cart.push({book, quantity: count});
  draftId = '';
  saveCart();
  renderTabs();
  if (current === 'cart') renderCart();
  if (change > 0 && current !== 'cart') showToast('Savatchaga qo‘shildi');
}

function catalogCard(book) {
  const images = bookImages(book);
  const heading = button(
    [artwork(book), images.length > 1 ? element('span', {
      class: 'photo-dots', 'aria-label': `${images.length} ta rasm`,
    }, ...images.slice(0, 5).map(() => element('i', {}))) : null],
    () => renderBook(book), 'cover-button', {'aria-label': book.title});
  return element('article', {class: 'card product'},
    heading,
    element('div', {class: 'product-info'}, element('h2', {}, book.title),
      stockBadge(book),
      element('div', {class: 'product-actions'},
        element('span', {class: 'price'}, won(book.price)),
        button('+', () => alterCart(book, 1), 'icon add',
          {'aria-label': book.title + ' savatchaga qo‘shish'}))),
  );
}

function catalogSearch() {
  const input = element('input', {type: 'search', placeholder: 'Kitob qidirish', 'aria-label': 'Kitob qidirish',
    value: searchText, enterkeyhint: 'search', oninput: event => { searchText = event.target.value; }});
  return element('form', {class: 'search', role: 'search',
    onsubmit: event => { event.preventDefault(); loadCatalog(searchText.trim()); }},
    glyph('search'), input, element('button', {type: 'submit', class: 'outline'}, 'Qidirish'));
}

function languageTabs() {
  const labels = interfaceLanguage === 'ru'
    ? {uz: 'Узбекский', en: 'Английский', ru: 'Русский'}
    : interfaceLanguage === 'en'
      ? {uz: 'Uzbek', en: 'English', ru: 'Russian'}
      : {uz: 'O‘zbekcha', en: 'Inglizcha', ru: 'Ruscha'};
  return element('div', {class: 'language-tabs', role: 'tablist', 'aria-label': t('Kitob tili')},
    ...languages.map(([code]) => button(labels[code], () => {
      if (bookLanguage === code) return;
      bookLanguage = code;
      localStorage.setItem(bookLanguageKey, code);
      catalog = {...catalog, books: [], loadedAt: 0, category: ''};
      loadCatalog('');
    }, 'language-tab', {'aria-selected': bookLanguage === code ? 'true' : 'false'})));
}

function catalogHeading() {
  return element('div', {class: 'row page-heading'}, element('h1', {}, 'Kitoblar'),
    button('Yangilash', () => loadCatalog(catalog.search), 'quiet'));
}

function catalogControls() {
  const categories = [...new Set(catalog.books.map(book => book.category).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
  const category = element('select', {'aria-label': t('Kategoriya'), onchange: event => {
    catalog.category = event.target.value;
    renderCatalog();
  }}, element('option', {value: ''}, 'Barcha kitoblar'),
  ...categories.map(value => element('option', {value}, value)));
  category.value = catalog.category;
  const sort = element('select', {'aria-label': t('Saralash'), onchange: event => {
    catalog.sort = event.target.value;
    renderCatalog();
  }},
  element('option', {value: 'new'}, 'Yangi qo‘shilgan'),
  element('option', {value: 'cheap'}, 'Narxi arzon'),
  element('option', {value: 'expensive'}, 'Narxi qimmat'),
  element('option', {value: 'title'}, 'Nom bo‘yicha'));
  sort.value = catalog.sort;
  return element('div', {class: 'catalog-controls'},
    labeled('Kategoriya', category), labeled('Saralash', sort));
}

function visibleCatalogBooks() {
  const result = catalog.category
    ? catalog.books.filter(book => book.category === catalog.category)
    : [...catalog.books];
  if (catalog.sort === 'cheap') result.sort((a, b) => a.price - b.price);
  else if (catalog.sort === 'expensive') result.sort((a, b) => b.price - a.price);
  else if (catalog.sort === 'title') result.sort((a, b) => a.title.localeCompare(b.title));
  else result.sort((a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned))
    || String(b.created_at || '').localeCompare(String(a.created_at || '')));
  return result;
}

function renderCatalog() {
  const visible = visibleCatalogBooks();
  const body = stack(catalogHeading(), catalogSearch(), languageTabs(),
    catalogControls(),
    catalog.search ? element('div', {class: 'filters'},
      button('Hammasi', () => loadCatalog(''), 'chip'),
      element('span', {class: 'status'}, '“' + catalog.search + '” natijalari')) : null,
    small(`${number.format(visible.length)} ${t('ta kitob')}`, 'catalog-count'),
    visible.length ? element('div', {class: 'grid'}, ...visible.map(catalogCard))
      : small('Kitob topilmadi.', 'status'),
  );
  display(body);
}

async function loadCatalog(search) {
  const request = ++navigation;
  searchText = search;
  display(stack(catalogHeading(), catalogSearch(), languageTabs(), small('Kitoblar yuklanmoqda…', 'status')));
  try {
    const result = await api('catalog', {search, language: bookLanguage});
    if (current !== 'books' || request !== navigation) return;
    const books = [...new Map(result.books.map(book => [book.id, book])).values()];
    catalog = {...catalog, books, search, loadedAt: Date.now()};
    if (cart.length) {
      const refreshed = new Map(result.books.map(book => [book.id, book]));
      let changed = false;
      for (const line of cart) {
        if (refreshed.has(line.book.id)) {
          line.book = refreshed.get(line.book.id);
          changed = true;
        }
      }
      if (changed) saveCart();
    }
    renderCatalog();
  } catch (failure) {
    if (current !== 'books' || request !== navigation) return;
    display(stack(catalogHeading(), catalogSearch(), small(failure.message, 'error'),
      button('Qayta urinish', () => loadCatalog(search))));
  }
}

function renderBook(book) {
  current = 'book';
  navigation++;
  renderTabs();
  window.scrollTo(0, 0);
  const images = bookImages(book);
  let selectedImage = 0;
  const gallery = element('div', {class: 'detail-gallery'});
  const redrawGallery = () => {
    const countLabel = element('span', {class: 'gallery-count'}, `${selectedImage + 1} / ${images.length}`);
    const track = element('div', {class: 'gallery-track'},
      ...(images.length ? images : [null]).map((source, index) =>
        element('div', {class: 'gallery-slide', 'aria-hidden': index === selectedImage ? 'false' : 'true'}, artwork(book, source))));
    let scrollFrame = 0;
    track.addEventListener('scroll', () => {
      cancelAnimationFrame(scrollFrame);
      scrollFrame = requestAnimationFrame(() => {
        if (!track.clientWidth || images.length < 2) return;
        selectedImage = Math.max(0, Math.min(images.length - 1,
          Math.round(track.scrollLeft / track.clientWidth)));
        countLabel.textContent = `${selectedImage + 1} / ${images.length}`;
      });
    }, {passive: true});
    track.scrollLeft = selectedImage * track.clientWidth;
    gallery.replaceChildren(track,
      images.length > 1 ? element('div', {class: 'gallery-footer'},
        button('‹', () => { selectedImage = (selectedImage - 1 + images.length) % images.length; redrawGallery(); }, 'gallery-arrow', {'aria-label': 'Oldingi rasm'}),
        countLabel,
        button('›', () => { selectedImage = (selectedImage + 1) % images.length; redrawGallery(); }, 'gallery-arrow', {'aria-label': 'Keyingi rasm'})) : null);
    requestAnimationFrame(() => { track.scrollLeft = selectedImage * track.clientWidth; });
  };
  redrawGallery();
  display(stack(
    button('‹ Kitoblar', () => changePage('books'), 'quiet back'),
    element('article', {class: 'card book-detail'},
      element('div', {class: 'detail-stage'}, gallery),
      element('div', {class: 'stack detail-info'},
        element('h1', {}, book.title),
        book.author || book.category ? small([book.author, book.category].filter(Boolean).join(' · ')) : null,
        element('div', {class: 'row detail-pricing'}, element('strong', {class: 'price'}, won(book.price)), stockBadge(book)),
        small(interfaceLanguage === 'ru'
          ? `Доставка для 1–3 книг — ${won(POSTAGE)}. ${FREE_POSTAGE_TEXT()}`
          : interfaceLanguage === 'en'
            ? `Delivery for 1–3 books is ${won(POSTAGE)}. ${FREE_POSTAGE_TEXT()}`
            : `1–3 ta kitobga pochta ${won(POSTAGE)}. ${FREE_POSTAGE_TEXT()}`, 'notice'),
        button('Savatchaga qo‘shish', () => alterCart(book, 1), 'primary'),
        book.description ? element('p', {class: 'detail-text'}, book.description) : null)),
  ));
}

function stepper(line) {
  return element('div', {class: 'stepper'},
    button('−', () => alterCart(line.book, -1), 'icon', {'aria-label': 'Bittaga kamaytirish'}),
    element('span', {}, String(line.quantity)),
    button('+', () => alterCart(line.book, 1), 'icon', {
      'aria-label': 'Bittaga ko‘paytirish',
      disabled: line.quantity >= line.book.stock || line.quantity >= 100,
    }));
}

function cartTotals(byPost = true) {
  let subtotal = 0;
  let quantity = 0;
  for (const line of cart) {
    subtotal += line.book.price * line.quantity;
    quantity += line.quantity;
  }
  const postage = byPost && quantity > 0 && quantity < FREE_POSTAGE_BOOKS ? POSTAGE : 0;
  return {subtotal, quantity, postage, total: subtotal + postage};
}

function totalsRows(totals, byPost = true) {
  return [
    element('div', {class: 'row'}, 'Kitoblar jami', won(totals.subtotal)),
    element('div', {class: 'row'}, byPost ? 'Pochta' : 'Olib ketish',
      totals.postage ? won(totals.postage) : 'Bepul'),
    element('div', {class: 'row summary'}, 'Jami',
      element('strong', {class: 'price'}, won(totals.total))),
  ];
}

function renderCart() {
  const totals = cartTotals();
  const rows = cart.map(line => element('article', {class: 'card cart-row'}, artwork(line.book),
    element('div', {class: 'stack'}, element('h2', {}, line.book.title),
      element('div', {class: 'row'}, element('span', {class: 'price'}, won(line.book.price * line.quantity)),
        stepper(line)))));
  display(stack(element('div', {class: 'row page-heading'}, element('h1', {}, 'Savatcha'),
    totals.quantity ? small(totals.quantity + ' dona', 'cart-total') : null), ...rows,
    cart.length ? small(FREE_POSTAGE_TEXT(), 'notice') : small('Savatcha bo‘sh.', 'status'),
    cart.length ? element('section', {class: 'card stack cart-summary'},
      ...totalsRows(totals),
      button('Buyurtma berish', () => renderCheckout(), 'primary')) : button('Kitoblarni ko‘rish', () => changePage('books'), 'primary')));
}

function orderItems() {
  return cart.map(line => ({book_id: line.book.id, quantity: line.quantity}));
}

function labeled(label, field) {
  return element('label', {}, element('span', {}, label), field);
}

function notificationPermission() {
  if (messageAccess || typeof telegram?.requestWriteAccess !== 'function'
      || telegram.isVersionAtLeast?.('6.9') === false) return null;
  const caption = element('p', {class: 'muted', role: 'status'},
    'Buyurtma qabul qilinganda va jo‘natilganda Telegramdan xabar oling.');
  const allow = button('Telegram xabarlarini yoqish', () => {
    allow.disabled = true;
    try {
      telegram.requestWriteAccess(granted => {
        allow.disabled = false;
        messageAccess = granted === true;
        allow.hidden = messageAccess;
        caption.textContent = messageAccess
          ? 'Telegram xabarlari yoqildi.'
          : 'Buyurtma holatini «Buyurtmalar» bo‘limida ko‘rishingiz mumkin.';
      });
    } catch (_) {
      allow.disabled = false;
      caption.textContent = 'Buyurtma holatini «Buyurtmalar» bo‘limida ko‘rishingiz mumkin.';
    }
  });
  return stack(caption, allow);
}

function renderCheckout(previous = {}) {
  current = 'checkout';
  navigation++;
  renderTabs();
  window.scrollTo(0, 0);
  const name = element('input', {name: 'name', autocomplete: 'name', maxlength: 100, required: true, value: previous.name});
  const phone = element('input', {type: 'tel', autocomplete: 'tel', maxlength: 32, required: true, value: previous.phone});
  const address = element('input', {autocomplete: 'street-address', maxlength: 500, required: true, value: previous.address, placeholder: 'Koreyadagi to‘liq manzil'});
  const delivery = element('select', {},
    element('option', {value: '택배'}, 'Pochta orqali'),
    element('option', {value: '경산 직접수령'}, 'Gyeongsan’da olib ketish'));
  if (previous.delivery) delivery.value = previous.delivery;
  const addressLabel = labeled('Manzil', address);
  const totals = stack();
  totals.setAttribute('aria-live', 'polite');
  function updateDelivery() {
    const ship = delivery.value === '택배';
    addressLabel.hidden = !ship;
    address.required = ship;
    totals.replaceChildren(...totalsRows(cartTotals(ship), ship));
  }
  delivery.addEventListener('change', updateDelivery);
  updateDelivery();
  const progress = small('', 'error');
  const quoteButton = element('button', {type: 'submit', class: 'primary'}, 'Jami summani ko‘rish');
  const form = element('form', {class: 'stack card', onsubmit: async event => {
    event.preventDefault();
    if (pending) return;
    pending = true;
    quoteButton.disabled = true;
    progress.textContent = '';
    const details = {
      name: name.value, phone: phone.value, address: address.required ? address.value : '',
      delivery: delivery.value, items: orderItems(),
    };
    try {
      const quote = await api('quote', details);
      renderPayment(details, quote);
    } catch (failure) {
      progress.textContent = failure.message;
    } finally {
      pending = false;
      quoteButton.disabled = false;
    }
  }}, labeled('Ism', name), labeled('Telefon raqami', phone), labeled('Yetkazish', delivery),
    addressLabel, totals, notificationPermission(), quoteButton, progress);
  display(stack(element('div', {class: 'row'}, button('‹ Savatcha', () => { if (!pending) changePage('cart'); }),
    element('h1', {}, 'Buyurtma')), form));
}

function imageBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Chek rasmini o‘qib bo‘lmadi.'));
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.readAsDataURL(file);
  });
}

function renderPayment(details, quote) {
  const upload = element('input', {type: 'file', accept: 'image/jpeg,image/png,image/webp', required: true});
  const submit = element('button', {type: 'submit', class: 'primary'}, 'Chekni yuborish');
  const message = small('', 'error');
  const back = button('‹ Ma’lumotlar', () => { if (!pending) renderCheckout(details); });
  const edit = button('Summani qayta tekshirish', () => renderCheckout(details), 'outline', {hidden: true});
  const form = element('form', {class: 'stack card', onsubmit: async event => {
    event.preventDefault();
    if (pending) return;
    const file = upload.files[0];
    if (!file || file.size > 5 * 1024 * 1024 || !['image/jpeg','image/png','image/webp'].includes(file.type)) {
      message.textContent = '5 MB gacha JPG, PNG yoki WEBP chek rasmini tanlang.';
      return;
    }
    pending = true;
    submit.disabled = true;
    edit.hidden = true;
    message.textContent = 'Chek yuborilmoqda…';
    draftId ||= crypto.randomUUID();
    saveCart();
    try {
      const order = await api('order', {
        ...details, id: draftId, total: quote.total,
        receipt_type: file.type, receipt_image: await imageBase64(file),
      });
      cart = [];
      draftId = '';
      saveCart();
      renderOrderConfirmation(order);
    } catch (failure) {
      message.textContent = failure.message;
      edit.hidden = failure.status !== 409;
    } finally {
      pending = false;
      submit.disabled = false;
    }
  }}, labeled('To‘lov cheki', upload), submit, edit, message);
  const bank = element('span', {class: 'copy-field'}, [quote.bank.name, quote.bank.number, quote.bank.owner].join(' · '));
  const copy = button('Hisob raqamini nusxalash', async () => {
    try {
      await navigator.clipboard.writeText(quote.bank.number);
      showToast('Hisob raqami nusxalandi');
    } catch (_) {
      showToast('Hisob raqamini belgilab nusxalashingiz mumkin.');
    }
  });
  display(stack(element('div', {class: 'row'}, back, element('h1', {}, 'To‘lov')),
    element('div', {class: 'card stack'},
      element('div', {class: 'row'}, 'Kitoblar', won(quote.subtotal)),
      element('div', {class: 'row'}, 'Yetkazish', quote.delivery_fee ? won(quote.delivery_fee) : 'Bepul'),
      element('div', {class: 'row summary'}, 'Jami', element('strong', {class: 'price'}, won(quote.total))),
      bank, copy), form));
}

function orderCard(order) {
  const stages = ['Qabul qilindi', 'Tayyorlandi', 'Jo‘natildi'];
  const phase = order.status === 'shipping' ? 2 : order.prepared ? 1
    : ['accepted','paid','preparing'].includes(order.status) ? 0 : -1;
  const cancelled = order.status === 'cancelled';
  const status = cancelled ? 'Bekor qilindi' : phase < 0 ? 'Tekshirilmoqda' : stages[phase];
  return element('article', {class: 'card stack'},
    element('div', {class: 'row order-head'},
      element('h2', {}, order.number ? 'Buyurtma #' + order.number : 'Buyurtma'),
      element('span', {class: 'phase'}, status)),
    element('strong', {class: 'price'}, won(order.total)),
    !cancelled ? element('ol', {class: 'timeline'}, ...stages.map((stage, index) =>
      element('li', {class: index <= phase ? 'done' : ''}, (index <= phase ? '✓ ' : '○ ') + stage))) : null,
    ...order.items.map(item => element('div', {class: 'row order-line'}, item.title || 'Kitob',
      element('span', {}, item.quantity + ' × ' + won(item.price)))),
    order.tracking_number ? small([order.carrier, 'Trek-raqam ' + order.tracking_number].filter(Boolean).join(' · ')) : null,
  );
}

function renderOrderConfirmation(order) {
  current = 'orders';
  navigation++;
  renderTabs();
  window.scrollTo(0, 0);
  display(stack(element('h1', {}, 'Buyurtma yuborildi'), orderCard(order),
    button('Buyurtmalarim', () => changePage('orders'), 'primary')));
}

async function loadOrders(offset, existing = [], moreButton) {
  const request = ++navigation;
  if (moreButton) moreButton.disabled = true;
  else display(stack(element('h1', {}, 'Buyurtmalar'), small('Yuklanmoqda…', 'status')));
  try {
    const result = await api('orders', {offset});
    if (current !== 'orders' || request !== navigation) return;
    const orders = [...new Map([...existing, ...result.orders].map(order => [order.id, order])).values()];
    display(stack(element('div', {class: 'row'}, element('h1', {}, 'Buyurtmalar'),
      button('Yangilash', () => loadOrders(0))),
      ...orders.map(orderCard), orders.length ? null : small('Mini App orqali berilgan buyurtmalar shu yerda ko‘rinadi.', 'status'),
      result.more ? button('Yana buyurtmalar', event => loadOrders(offset + 20, orders, event.currentTarget)) : null));
  } catch (failure) {
    if (current !== 'orders' || request !== navigation) return;
    display(stack(element('h1', {}, 'Buyurtmalar'), small(failure.message, 'error'),
      button('Qayta urinish', () => loadOrders(0))));
  }
}

function languageChoice(selected, onChange) {
  return element('div', {class: 'language-choices'},
    ...languages.map(([code, label]) => element('button', {
      type: 'button', class: 'language-choice', onclick: () => onChange(code),
      'aria-pressed': selected === code ? 'true' : 'false',
    }, element('span', {class: 'radio', 'aria-hidden': 'true'}), label)));
}

function renderOnboarding() {
  current = 'onboarding';
  tabs.hidden = true;
  let selected = interfaceLanguage || 'uz';
  const choices = element('div');
  const redraw = () => choices.replaceChildren(languageChoice(selected, code => {
    selected = code;
    redraw();
  }));
  redraw();
  display(element('section', {class: 'language-page'},
    element('img', {class: 'language-logo', src: './muhajeer-logo.jpg', width: 86, height: 86, alt: ''}),
    element('strong', {class: 'language-brand'}, 'Muhajeer Books'),
    element('h1', {}, 'Tilni tanlang'), choices,
    button('Davom etish', () => {
      interfaceLanguage = selected;
      bookLanguage = selected;
      localStorage.setItem(languageKey, selected);
      localStorage.setItem(bookLanguageKey, selected);
      tabs.hidden = false;
      changePage('books');
    }, 'primary language-save')));
}

function renderLanguageSettings() {
  let selected = interfaceLanguage;
  const choices = element('div');
  const redraw = () => choices.replaceChildren(languageChoice(selected, code => {
    selected = code;
    redraw();
  }));
  redraw();
  display(element('section', {class: 'language-page settings'},
    element('h1', {}, 'Ilova tili'), choices,
    button('Saqlash', () => {
      interfaceLanguage = selected;
      localStorage.setItem(languageKey, selected);
      renderTabs();
      renderLanguageSettings();
      showToast(interfaceLanguage === 'ru' ? 'Язык сохранён'
        : interfaceLanguage === 'en' ? 'Language saved' : 'Til saqlandi');
    }, 'primary language-save')));
}

if (telegram?.initData) {
  telegram.ready();
  telegram.expand();
  if (interfaceLanguage) {
    tabs.hidden = false;
    changePage('books');
  } else {
    renderOnboarding();
  }
} else {
  display(stack(element('h1', {}, 'Muhajeer Books'),
    small('Do‘konni ochish uchun Telegram botidagi «Do‘konni ochish» tugmasini bosing.', 'status')));
}
