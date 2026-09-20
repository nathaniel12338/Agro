/*
  script.js
  ---------
  Self-contained floating chat widget for the Agricultural Chatbot.

  This file builds its own HTML, so embedding it anywhere (including a
  PHP site) is just 2 lines in the page:

      <link rel="stylesheet" href="style.css">
      <script src="script.js"></script>

  To point the widget at your backend, set this BEFORE the script tag:

      <script>window.AGRI_CHATBOT_API = "https://your-api-domain.com";</script>
      <link rel="stylesheet" href="style.css">
      <script src="script.js"></script>

  If you don't set it, the widget defaults to http://127.0.0.1:8000
  (useful for local testing).
*/

(function () {
  "use strict";

  // ------------------------------------------------------------------
  // CONFIG
  // ------------------------------------------------------------------

  const API_BASE = (
  window.AGRI_CHATBOT_API ||
  "https://agro-production-bed1.up.railway.app"
).replace(/\/$/, "");

  // ------------------------------------------------------------------
  // ICONS (inline SVG so no external icon library is needed)
  // ------------------------------------------------------------------

  const ICON_LEAF =
    '<svg class="agri-icon-leaf" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M20 4C10 4 4 10 4 18v2h2c8 0 14-6 14-16V4z" fill="#FFFFFF"/>' +
    '<path d="M6 20C10 16 14 12 19 5" stroke="#2F7D52" stroke-width="1.4" stroke-linecap="round"/>' +
    "</svg>";

  const ICON_CHAT =
    '<svg class="agri-icon-chat" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M6 18L4 20V6a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H6z" stroke="#FFFFFF" stroke-width="1.6" stroke-linejoin="round"/>' +
    "</svg>";

  const ICON_SEND =
    '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M4 12l16-8-6 16-3-6-7-2z" fill="#FFFFFF"/>' +
    "</svg>";

  const ICON_CLOSE =
    '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M6 6l12 12M18 6L6 18" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>' +
    "</svg>";

  const ICON_HEADER =
    '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M20 4C10 4 4 10 4 18v2h2c8 0 14-6 14-16V4z" fill="#B7E4C7"/>' +
    "</svg>";

  // ------------------------------------------------------------------
  // BUILD THE WIDGET DOM
  // ------------------------------------------------------------------

  function buildWidget() {
    const root = document.createElement("div");
    root.id = "agri-chat-root";
    root.innerHTML =
      '<button class="agri-launcher" id="agri-launcher" aria-label="Open farming assistant chat">' +
      ICON_LEAF +
      ICON_CHAT +
      "</button>" +
      '<div class="agri-panel" id="agri-panel">' +
      '  <div class="agri-header">' +
      '    <div class="agri-header-icon">' + ICON_HEADER + "</div>" +
      '    <div class="agri-header-text">' +
      '      <div class="agri-header-title">Farm Assistant</div>' +
      '      <div class="agri-header-subtitle">Crops, pests &amp; the produce market</div>' +
      "    </div>" +
      '    <button class="agri-close-btn" id="agri-close" aria-label="Close chat">' + ICON_CLOSE + "</button>" +
      "  </div>" +
      '  <div class="agri-messages" id="agri-messages"></div>' +
      '  <div class="agri-input-row">' +
      '    <input type="text" id="agri-input" placeholder="Type your question..." autocomplete="off" />' +
      '    <button class="agri-send-btn" id="agri-send" aria-label="Send message">' + ICON_SEND + "</button>" +
      "  </div>" +
      "</div>";
    document.body.appendChild(root);
    return root;
  }

  // ------------------------------------------------------------------
  // CONVERSATION STATE
  // ------------------------------------------------------------------
  // The widget can be in one of these modes:
  //   "idle"        -> free-form questions go to /chat
  //   "sell_*"      -> collecting seller fields step by step
  //   "buy_product" -> waiting for the product name to search for
  const SELL_STEPS = ["product_name", "quantity", "location", "price", "phone"];
  const SELL_PROMPTS = {
    product_name: "What produce do you want to sell? (e.g. Maize, Tomato, Cassava)",
    quantity: "How much do you have available? (e.g. 20 bags, 500kg)",
    location: "Where is it located? (e.g. Kano, Oyo State)",
    price: "What is your price? (e.g. ₦25,000 per bag)",
    phone: "What phone number should buyers contact you on?",
  };

  let state = {
    mode: "idle",
    sellData: {},
  };

  // ------------------------------------------------------------------
  // UI HELPERS
  // ------------------------------------------------------------------

  function el(root, id) {
    return root.querySelector("#" + id);
  }

  function addBotMessage(messagesEl, html) {
    const div = document.createElement("div");
    div.className = "agri-msg agri-msg-bot";
    div.innerHTML = html;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function addUserMessage(messagesEl, text) {
    const div = document.createElement("div");
    div.className = "agri-msg agri-msg-user";
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addQuickReplies(messagesEl, options, onPick) {
    const wrap = document.createElement("div");
    wrap.className = "agri-quick-replies";
    options.forEach(function (opt) {
      const btn = document.createElement("button");
      btn.className = "agri-chip";
      btn.type = "button";
      btn.textContent = opt.label;
      btn.addEventListener("click", function () {
        onPick(opt);
      });
      wrap.appendChild(btn);
    });
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function showTyping(messagesEl) {
    const div = document.createElement("div");
    div.className = "agri-typing";
    div.id = "agri-typing-indicator";
    div.innerHTML = "<span></span><span></span><span></span>";
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function removeTyping(messagesEl) {
    const typing = messagesEl.querySelector("#agri-typing-indicator");
    if (typing) typing.remove();
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // ------------------------------------------------------------------
  // MAIN MENU
  // ------------------------------------------------------------------

  function showMainMenu(messagesEl) {
    addQuickReplies(
      messagesEl,
      [
        { label: "🌱 Ask a farming question", action: "ask" },
        { label: "💰 Sell my produce", action: "sell" },
        { label: "🛒 Buy produce", action: "buy" },
      ],
      function (opt) {
        if (opt.action === "ask") {
          addBotMessage(
            messagesEl,
            "Go ahead, type your question below — for example \"when should I plant maize\" or \"how I go control pest for tomato\"."
          );
        } else if (opt.action === "sell") {
          startSellFlow(messagesEl);
        } else if (opt.action === "buy") {
          startBuyFlow(messagesEl);
        }
      }
    );
  }

  // ------------------------------------------------------------------
  // SELL FLOW
  // ------------------------------------------------------------------

  function startSellFlow(messagesEl) {
    state.mode = "sell_product_name";
    state.sellData = {};
    addBotMessage(messagesEl, "Great, let's list your produce for sale. " + SELL_PROMPTS.product_name);
  }

  function handleSellStep(messagesEl, userText) {
    const currentField = state.mode.replace("sell_", "");
    state.sellData[currentField] = userText;

    const currentIndex = SELL_STEPS.indexOf(currentField);
    const nextField = SELL_STEPS[currentIndex + 1];

    if (nextField) {
      state.mode = "sell_" + nextField;
      addBotMessage(messagesEl, SELL_PROMPTS[nextField]);
    } else {
      // All fields collected -- submit to backend
      submitSellListing(messagesEl);
    }
  }

  function submitSellListing(messagesEl) {
    const typing = showTyping(messagesEl);

    fetch(API_BASE + "/sell", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.sellData),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed");
        return res.json();
      })
      .then(function () {
        removeTyping(messagesEl);
        addBotMessage(
          messagesEl,
          "✅ Your listing has been saved! Buyers looking for <strong>" +
            escapeHtml(state.sellData.product_name) +
            "</strong> will be able to find your contact details."
        );
        state.mode = "idle";
        state.sellData = {};
        showMainMenu(messagesEl);
      })
      .catch(function () {
        removeTyping(messagesEl);
        addBotMessage(
          messagesEl,
          "Sorry, I couldn't save your listing right now. Please check your connection and try again."
        );
        state.mode = "idle";
      });
  }

  // ------------------------------------------------------------------
  // BUY FLOW
  // ------------------------------------------------------------------

  function startBuyFlow(messagesEl) {
    state.mode = "buy_product";
    addBotMessage(messagesEl, "What produce are you looking to buy? (e.g. Maize, Tomato, Rice, Cassava)");
  }

  function handleBuyStep(messagesEl, userText) {
    const typing = showTyping(messagesEl);

    fetch(API_BASE + "/buy?product=" + encodeURIComponent(userText))
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed");
        return res.json();
      })
      .then(function (sellers) {
        removeTyping(messagesEl);

        if (!sellers || sellers.length === 0) {
          addBotMessage(
            messagesEl,
            "No sellers found for <strong>" + escapeHtml(userText) + "</strong> yet. Please check back later."
          );
        } else {
          addBotMessage(messagesEl, "Here's what I found for <strong>" + escapeHtml(userText) + "</strong>:");
          sellers.forEach(function (seller) {
            const card = document.createElement("div");
            card.className = "agri-msg agri-msg-bot agri-seller-card";
            card.innerHTML =
              "<div><strong>" + escapeHtml(seller.product_name) + "</strong></div>" +
              "<div>Quantity: " + escapeHtml(seller.quantity) + "</div>" +
              "<div>Location: " + escapeHtml(seller.location) + "</div>" +
              "<div>Price: " + escapeHtml(seller.price) + "</div>" +
              "<div>Contact: " + escapeHtml(seller.phone) + "</div>";
            messagesEl.appendChild(card);
          });
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        state.mode = "idle";
        showMainMenu(messagesEl);
      })
      .catch(function () {
        removeTyping(messagesEl);
        addBotMessage(messagesEl, "Sorry, I couldn't search for sellers right now. Please try again.");
        state.mode = "idle";
      });
  }

  // ------------------------------------------------------------------
  // FREE-FORM Q&A (/chat)
  // ------------------------------------------------------------------

  function handleChatQuestion(messagesEl, userText) {
    const typing = showTyping(messagesEl);

    fetch(API_BASE + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: userText }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed");
        return res.json();
      })
      .then(function (data) {
        removeTyping(messagesEl);
        addBotMessage(messagesEl, escapeHtml(data.reply));
        showMainMenu(messagesEl);
      })
      .catch(function () {
        removeTyping(messagesEl);
        addBotMessage(
          messagesEl,
          "Sorry, I couldn't reach the server just now. Please check that the backend is running and try again."
        );
      });
  }

  // ------------------------------------------------------------------
  // INPUT ROUTER
  // ------------------------------------------------------------------

  function handleUserInput(messagesEl, text) {
    addUserMessage(messagesEl, text);

    if (state.mode.startsWith("sell_")) {
      handleSellStep(messagesEl, text);
    } else if (state.mode === "buy_product") {
      handleBuyStep(messagesEl, text);
    } else {
      handleChatQuestion(messagesEl, text);
    }
  }

  // ------------------------------------------------------------------
  // INIT
  // ------------------------------------------------------------------

  function init() {
    const root = buildWidget();
    const launcher = el(root, "agri-launcher");
    const closeBtn = el(root, "agri-close");
    const panel = el(root, "agri-panel");
    const messagesEl = el(root, "agri-messages");
    const input = el(root, "agri-input");
    const sendBtn = el(root, "agri-send");

    let greeted = false;

    function openPanel() {
      root.classList.add("agri-open");
      if (!greeted) {
        greeted = true;
        addBotMessage(
          messagesEl,
          "👋 Hello, welcome! I'm your farm assistant. I can answer questions about maize, rice, cassava and tomato, or help you buy and sell produce."
        );
        showMainMenu(messagesEl);
      }
      input.focus();
    }

    function closePanel() {
      root.classList.remove("agri-open");
    }

    launcher.addEventListener("click", function () {
      if (root.classList.contains("agri-open")) {
        closePanel();
      } else {
        openPanel();
      }
    });

    closeBtn.addEventListener("click", closePanel);

    function submitInput() {
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      handleUserInput(messagesEl, text);
    }

    sendBtn.addEventListener("click", submitInput);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") submitInput();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
