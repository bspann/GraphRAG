/**
 * RAG Chat Application - Frontend JavaScript
 * Handles chat interactions, message rendering, and API communication
 */

// =============================================================================
// State
// =============================================================================

let sessionId = window.SESSION_ID || null;
let isLoading = false;

// =============================================================================
// DOM Elements
// =============================================================================

const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const messagesContainer = document.getElementById('messages-container');
const welcomeMessage = document.getElementById('welcome-message');
const newChatBtn = document.getElementById('new-chat-btn');
const newChatMobileBtn = document.getElementById('new-chat-mobile');
const sessionDisplay = document.getElementById('session-display');

// Templates
const loadingTemplate = document.getElementById('loading-template');
const userMessageTemplate = document.getElementById('user-message-template');
const assistantMessageTemplate = document.getElementById('assistant-message-template');
const sourceTemplate = document.getElementById('source-template');

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Load existing chat history
    loadChatHistory();
    
    // Set up event listeners
    chatForm.addEventListener('submit', handleSubmit);
    userInput.addEventListener('keydown', handleKeyDown);
    userInput.addEventListener('input', autoResizeTextarea);
    newChatBtn?.addEventListener('click', startNewChat);
    newChatMobileBtn?.addEventListener('click', startNewChat);
    
    // Focus input
    userInput.focus();
});

// =============================================================================
// API Functions
// =============================================================================

/**
 * Send a message to the chat API
 */
async function sendMessage(message) {
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            message: message,
            session_id: sessionId
        })
    });
    
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
}

/**
 * Load chat history from the API
 */
async function loadChatHistory() {
    if (!sessionId) return;
    
    try {
        const response = await fetch(`/api/history/${sessionId}`);
        if (!response.ok) return;
        
        const data = await response.json();
        
        if (data.messages && data.messages.length > 0) {
            // Hide welcome message
            welcomeMessage?.classList.add('hidden');
            
            // Render existing messages
            data.messages.forEach(msg => {
                if (msg.role === 'user') {
                    appendUserMessage(msg.content);
                } else if (msg.role === 'assistant') {
                    appendAssistantMessage(msg.content, msg.sources || []);
                }
            });
            
            scrollToBottom();
        }
    } catch (error) {
        console.error('Failed to load chat history:', error);
    }
}

/**
 * Create a new chat session
 */
async function startNewChat() {
    try {
        const response = await fetch('/api/sessions', {
            method: 'POST'
        });
        
        if (response.ok) {
            const data = await response.json();
            sessionId = data.session_id;
            
            // Update display
            if (sessionDisplay) {
                sessionDisplay.textContent = sessionId;
            }
            
            // Clear messages
            clearMessages();
            
            // Show welcome message
            welcomeMessage?.classList.remove('hidden');
            
            // Focus input
            userInput.focus();
        }
    } catch (error) {
        console.error('Failed to create new session:', error);
    }
}

// =============================================================================
// Event Handlers
// =============================================================================

/**
 * Handle form submission
 */
async function handleSubmit(event) {
    event.preventDefault();
    
    const message = userInput.value.trim();
    if (!message || isLoading) return;
    
    // Hide welcome message
    welcomeMessage?.classList.add('hidden');
    
    // Clear input and reset height
    userInput.value = '';
    userInput.style.height = 'auto';
    
    // Add user message
    appendUserMessage(message);
    
    // Show loading indicator
    showLoading();
    
    try {
        // Send to API
        const response = await sendMessage(message);
        
        // Remove loading indicator
        hideLoading();
        
        // Add assistant response
        appendAssistantMessage(response.response, response.sources || []);
        
        // Update session ID if changed
        if (response.session_id) {
            sessionId = response.session_id;
            if (sessionDisplay) {
                sessionDisplay.textContent = sessionId;
            }
        }
        
    } catch (error) {
        console.error('Chat error:', error);
        hideLoading();
        appendAssistantMessage(
            'Sorry, I encountered an error processing your request. Please try again.',
            []
        );
    }
    
    // Scroll to bottom
    scrollToBottom();
    
    // Focus input
    userInput.focus();
}

/**
 * Handle keyboard shortcuts
 */
function handleKeyDown(event) {
    // Submit on Enter (without Shift)
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
}

/**
 * Auto-resize textarea based on content
 */
function autoResizeTextarea() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
}

// =============================================================================
// Message Rendering
// =============================================================================

/**
 * Append a user message to the chat
 */
function appendUserMessage(content) {
    const template = userMessageTemplate.content.cloneNode(true);
    const messageContent = template.querySelector('.message-content');
    messageContent.textContent = content;
    messagesContainer.appendChild(template);
}

/**
 * Append an assistant message to the chat
 */
function appendAssistantMessage(content, sources) {
    const template = assistantMessageTemplate.content.cloneNode(true);
    const messageContent = template.querySelector('.message-content');
    
    // Render markdown content
    messageContent.innerHTML = marked.parse(content);
    
    // Handle sources
    if (sources && sources.length > 0) {
        const sourcesContainer = template.querySelector('.sources-container');
        const sourcesToggle = template.querySelector('.sources-toggle');
        const sourcesCount = template.querySelector('.sources-count');
        const sourcesList = template.querySelector('.sources-list');
        const sourcesIcon = template.querySelector('.sources-icon');
        
        sourcesContainer.classList.remove('hidden');
        sourcesCount.textContent = `View ${sources.length} Source${sources.length > 1 ? 's' : ''}`;
        
        // Add source items
        sources.forEach(source => {
            const sourceEl = sourceTemplate.content.cloneNode(true);
            sourceEl.querySelector('.source-title').textContent = source.title || 'Untitled';
            sourceEl.querySelector('.source-content').textContent = source.content || '';
            sourcesList.appendChild(sourceEl);
        });
        
        // Toggle sources visibility
        sourcesToggle.addEventListener('click', () => {
            sourcesList.classList.toggle('hidden');
            sourcesIcon.classList.toggle('rotate-90');
        });
    }
    
    messagesContainer.appendChild(template);
}

/**
 * Show loading indicator
 */
function showLoading() {
    isLoading = true;
    sendBtn.disabled = true;
    
    const template = loadingTemplate.content.cloneNode(true);
    messagesContainer.appendChild(template);
    scrollToBottom();
}

/**
 * Hide loading indicator
 */
function hideLoading() {
    isLoading = false;
    sendBtn.disabled = false;
    
    const loadingIndicator = messagesContainer.querySelector('.loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.remove();
    }
}

/**
 * Clear all messages
 */
function clearMessages() {
    // Remove all children except welcome message
    const children = Array.from(messagesContainer.children);
    children.forEach(child => {
        if (child.id !== 'welcome-message') {
            child.remove();
        }
    });
}

/**
 * Scroll to the bottom of the messages container
 */
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}
