'use strict';

const telegram = window.Telegram?.WebApp;
const view = document.getElementById('view');
const tabs = document.getElementById('tabs');
const toast = document.getElementById('toast');
const won = amount => '₩' + new Intl.NumberFormat('en-US').format(amount || 0);
const names = [['books','📚','Kitoblar'],['cart','🛒','Savatcha'],['orders','▤','Buyurtmalar']];
const storageKey = 'muhajeer-mini-cart-' + (telegram?.initDataUnsafe?.user?.id || 'browser');
const persisted = readCart();
let cart = persisted.cart;
let draftId = persisted.draftId;
let current = 'books';
let catalog = {books: [], more: false, search: '', offset: 0, loaded: false};
let searchText = '';
let pending = false;
let navigation = 0;
let toastTimer;

function element(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value !== false && value !== undefined && value !== null) {
      node.setAttribute(key, value === true ? '' : value);
    }
  }
  node.append(...children.flat().filter(child => child !== null && child !== undefined));
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
    if (catalog.loaded) renderCatalog();
    else loadCatalog('', 0);
  }
  if (page === 'cart') renderCart();
  if (page === 'orders') loadOrders(0);
}

function renderTabs() {
  const count = cart.reduce((sum, line) => sum + line.quantity, 0);
  tabs.replaceChildren(...names.map(([page, icon, title]) => {
    const active = current === page || current === 'book' && page === 'books'
      || current === 'checkout' && page === 'cart';
    return button(
      element('span', {}, element('span', {'aria-hidden': true}, icon),
        page === 'cart' && count ? title + ' (' + count + ')' : title),
      () => { if (!pending) changePage(page); },
      'tab', {'aria-current': active ? 'page' : null},
    );
  }));
}

function artwork(book) {
  const placeholder = element('div', {class: 'cover placeholder', 'aria-hidden': true}, book.title);
  if (typeof book.cover !== 'string' || !book.cover.startsWith('https://')) return placeholder;
  const image = element('img', {
    class: 'cover', src: book.cover, alt: '', loading: 'lazy', decoding: 'async',
    referrerpolicy: 'no-referrer', width: 240, height: 300,
  });
  image.addEventListener('error', () => image.replaceWith(placeholder), {once: true});
  return image;
}

function alterCart(book, change) {
  const found = cart.find(line => line.book.id === book.id);
  const count = (found?.quantity || 0) + change;
  if (count > book.stock || count > 100) {
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
  return element('article', {class: 'card product'},
    button(artwork(book), () => renderBook(book), 'cover-button', {'aria-label': book.title}),
    element('h2', {}, book.title),
    element('div', {class: 'row'}, element('span', {class: 'price'}, won(book.price)),
      button('+', () => alterCart(book, 1), 'icon', {'aria-label': book.title + ' savatchaga qo‘shish'})),
  );
}

function catalogSearch() {
  const input = element('input', {type: 'search', placeholder: 'Kitob qidirish', 'aria-label': 'Kitob qidirish',
    value: searchText, enterkeyhint: 'search', oninput: event => { searchText = event.target.value; }});
  return element('form', {class: 'inline-form',
    onsubmit: event => { event.preventDefault(); loadCatalog(searchText.trim(), 0); }},
    input, element('button', {type: 'submit', class: 'outline'}, 'Qidirish'));
}

function renderCatalog() {
  const body = stack(element('h1', {}, 'Kitoblar'), catalogSearch(),
    catalog.search ? element('div', {class: 'filters'},
      button('Hammasi', () => loadCatalog('', 0), 'chip'),
      element('span', {class: 'status'}, '“' + catalog.search + '” natijalari')) : null,
    catalog.books.length ? element('div', {class: 'grid'}, ...catalog.books.map(catalogCard))
      : small('Kitob topilmadi.', 'status'),
    catalog.more ? button('Yana kitoblar', event => loadCatalog(catalog.search, catalog.offset + 24, event.currentTarget)) : null,
  );
  display(body);
}

async function loadCatalog(search, offset, moreButton) {
  const request = ++navigation;
  searchText = search;
  if (moreButton) moreButton.disabled = true;
  else display(stack(element('h1', {}, 'Kitoblar'), catalogSearch(), small('Kitoblar yuklanmoqda…', 'status')));
  try {
    const result = await api('catalog', {search, offset});
    if (current !== 'books' || request !== navigation) return;
    const combined = offset > 0 ? [...catalog.books, ...result.books] : result.books;
    const books = [...new Map(combined.map(book => [book.id, book])).values()];
    catalog = {books, more: result.more, search, offset, loaded: true};
    renderCatalog();
  } catch (failure) {
    if (current !== 'books' || request !== navigation) return;
    display(stack(element('h1', {}, 'Kitoblar'), catalogSearch(), small(failure.message, 'error'),
      button('Qayta urinish', () => loadCatalog(search, 0))));
  }
}

function renderBook(book) {
  current = 'book';
  navigation++;
  renderTabs();
  window.scrollTo(0, 0);
  display(stack(
    element('div', {class: 'row'}, button('‹ Ortga', () => changePage('books')),
      element('h1', {}, book.title)),
    element('div', {class: 'detail-cover'}, artwork(book)),
    small(book.author || book.category || ''),
    element('div', {class: 'row'}, element('strong', {class: 'price'}, won(book.price)),
      element('span', {class: 'phase'}, 'Omborda bor')),
    book.description ? element('p', {class: 'detail-text'}, book.description) : null,
    button('Savatchaga qo‘shish', () => alterCart(book, 1), 'primary'),
  ));
}

function stepper(line) {
  return element('div', {class: 'stepper'},
    button('−', () => alterCart(line.book, -1), 'icon', {'aria-label': 'Bittaga kamaytirish'}),
    element('span', {}, String(line.quantity)),
    button('+', () => alterCart(line.book, 1), 'icon', {'aria-label': 'Bittaga ko‘paytirish'}));
}

function renderCart() {
  const amount = cart.reduce((sum, line) => sum + line.book.price * line.quantity, 0);
  const rows = cart.map(line => element('article', {class: 'card cart-row'}, artwork(line.book),
    element('div', {class: 'stack'}, element('h2', {}, line.book.title),
      element('div', {class: 'row'}, element('span', {class: 'price'}, won(line.book.price * line.quantity)),
        stepper(line)))));
  display(stack(element('h1', {}, 'Savatcha'), ...rows,
    cart.length ? element('p', {class: 'notice'}, '4 ta kitobdan boshlab bepul pochta shartlari buyurtmada tekshiriladi.') : small('Savatcha bo‘sh.', 'status'),
    cart.length ? element('div', {class: 'row summary'}, 'Kitoblar jami', element('strong', {}, won(amount))) : null,
    cart.length ? button('Buyurtma berish', () => renderCheckout(), 'primary') : button('Kitoblarni ko‘rish', () => changePage('books'), 'primary')));
}

function orderItems() {
  return cart.map(line => ({book_id: line.book.id, quantity: line.quantity}));
}

function labeled(label, field) {
  return element('label', {}, element('span', {}, label), field);
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
  function updateDelivery() {
    const ship = delivery.value === '택배';
    addressLabel.hidden = !ship;
    address.required = ship;
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
    addressLabel, quoteButton, progress);
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

if (telegram?.initData) {
  telegram.ready();
  telegram.expand();
  tabs.hidden = false;
  changePage('books');
} else {
  display(stack(element('h1', {}, 'Muhajeer Books'),
    small('Do‘konni ochish uchun Telegram botidagi «Do‘konni ochish» tugmasini bosing.', 'status')));
}
