document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const chatMessages = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const resetBtn = document.getElementById('reset-btn');
    const jobDetails = document.getElementById('job-details');
    const systemMessageTemplate = document.getElementById('system-message-template');
    const userMessageTemplate = document.getElementById('user-message-template');
    const welcomeMessageTemplate = document.getElementById('welcome-message-template');
    const themeToggle = document.getElementById('theme-toggle');
    const moonIcon = document.getElementById('moon-icon');
    const sunIcon = document.getElementById('sun-icon');
    const progressBar = document.getElementById('progress-bar');
    const toggleDetailsBtn = document.getElementById('toggle-details');
    const jobDetailsContainer = document.querySelector('.job-details-container');
    
    // State
    let currentField = null;
    let typingTimeout = null;
    let completedFields = 0;
    let totalFields = 10; // Estimation du nombre total de champs à remplir
    
    // Check for saved theme preference or default to 'light'
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);
    
    // Initialize chat with welcome message
    initChat();
    
    // Check screen size and setup mobile view if needed
    checkScreenSize();
    window.addEventListener('resize', checkScreenSize);
    
    // Event listeners
    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
        
        // Auto resize textarea
        setTimeout(() => {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        }, 0);
    });
    
    resetBtn.addEventListener('click', resetChat);
    
    themeToggle.addEventListener('click', function() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
        localStorage.setItem('theme', newTheme);
    });
    
    if (toggleDetailsBtn) {
        toggleDetailsBtn.addEventListener('click', function() {
            jobDetailsContainer.classList.toggle('open');
        });
    }
    
    function setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        
        // Update toggle icon
        if (theme === 'dark') {
            moonIcon.style.display = 'none';
            sunIcon.style.display = 'block';
        } else {
            moonIcon.style.display = 'block';
            sunIcon.style.display = 'none';
        }
    }
    
    function checkScreenSize() {
        if (window.innerWidth <= 768) {
            toggleDetailsBtn.style.display = 'flex';
        } else {
            toggleDetailsBtn.style.display = 'none';
            jobDetailsContainer.classList.remove('open');
        }
    }
    
    function updateProgressBar(completed, total) {
        const percentage = Math.min(Math.round((completed / total) * 100), 100);
        progressBar.style.width = `${percentage}%`;
    }
    
    function initChat() {
        // Clear existing messages
        chatMessages.innerHTML = '';
        
        // Reset progress
        completedFields = 0;
        updateProgressBar(completedFields, totalFields);
        
        // Add welcome message
        const welcomeClone = welcomeMessageTemplate.content.cloneNode(true);
        chatMessages.appendChild(welcomeClone);
        
        // Show typing indicator and get first question
        showTypingIndicator();
        
        // Simulate delay before showing first question
        setTimeout(() => {
            // Make API call to get first message
            fetch('/api/message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: 'START' }),
            })
            .then(response => response.json())
            .then(data => {
                hideTypingIndicator();
                if (data.response) {
                    addSystemMessage(data.response);
                    currentField = data.field;
                    updateJobDetails(data.current_state);
                    
                    // Focus on input
                    userInput.focus();
                }
            })
            .catch(error => {
                hideTypingIndicator();
                console.error('Error:', error);
                addSystemMessage("Une erreur s'est produite. Veuillez réessayer.");
            });
        }, 1500);
    }
    
    function sendMessage() {
        const message = userInput.value.trim();
        if (message === '') return;
        
        // Add user message to chat
        addUserMessage(message);
        
        // Clear input and reset height
        userInput.value = '';
        userInput.style.height = 'auto';
        
        // Show typing indicator
        showTypingIndicator();
        
        // Send message to server
        fetch('/api/message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message }),
        })
        .then(response => response.json())
        .then(data => {
            hideTypingIndicator();
            if (data.response) {
                addSystemMessage(data.response);
                
                // Update field tracking
                if (data.field !== currentField) {
                    if (data.success) {
                        completedFields++;
                        updateProgressBar(completedFields, totalFields);
                    }
                    currentField = data.field;
                }
                
                if (data.current_state) {
                    updateJobDetails(data.current_state);
                }
            } else if (data.error) {
                addSystemMessage(`Erreur: ${data.error}`);
            }
        })
        .catch(error => {
            hideTypingIndicator();
            console.error('Error:', error);
            addSystemMessage("Une erreur s'est produite. Veuillez réessayer.");
        });
    }
    
    function resetChat() {
        // Animation de reset
        progressBar.style.width = '0%';
        
        // Clear UI
        jobDetails.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"></rect><line x1="16" x2="16" y1="2" y2="6"></line><line x1="8" x2="8" y1="2" y2="6"></line><line x1="3" x2="21" y1="10" y2="10"></line><path d="m9 16 2 2 4-4"></path></svg>
                </div>
                <div class="empty-state-text">
                    Les détails de l'offre apparaîtront ici au fur et à mesure de votre conversation avec l'assistant.
                </div>
            </div>
        `;
        
        // Reset session on server
        fetch('/api/reset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                initChat();
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
    }
    
    function addSystemMessage(message) {
        const messageClone = systemMessageTemplate.content.cloneNode(true);
        const messageContent = messageClone.querySelector('.message-content');
        messageContent.textContent = message;
        
        // Format JSON if found
        if (message.includes('{') && message.includes('}')) {
            const formattedMessage = formatJSONInMessage(message);
            if (formattedMessage) {
                messageContent.innerHTML = formattedMessage;
            }
        }
        
        chatMessages.appendChild(messageClone);
        scrollToBottom();
    }
    
    function addUserMessage(message) {
        const messageClone = userMessageTemplate.content.cloneNode(true);
        messageClone.querySelector('.message-content').textContent = message;
        chatMessages.appendChild(messageClone);
        scrollToBottom();
    }
    
    function showTypingIndicator() {
        if (document.querySelector('.typing-indicator')) return;
        
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.innerHTML = '<span></span><span></span><span></span>';
        chatMessages.appendChild(indicator);
        scrollToBottom();
    }
    
    function hideTypingIndicator() {
        const indicator = document.querySelector('.typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }
    
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function updateJobDetails(state) {
        if (!state || !state.jobDetails) return;
        
        const details = state.jobDetails;
        
        // Count filled fields for progress bar
        const filledFieldsCount = Object.values(details).filter(value => {
            return value !== null && value !== undefined && value !== '' && 
                  !(Array.isArray(value) && value.length === 0) && 
                  !(typeof value === 'object' && (!value || Object.keys(value).length === 0 || 
                   (value.name === null && (!('overlap' in value) || value.overlap === null))));
        }).length;
        
        completedFields = filledFieldsCount;
        updateProgressBar(completedFields, totalFields);
        
        // Organize fields into sections
        const basicInfo = {};
        const contractInfo = {};
        const locationInfo = {};
        const skillsInfo = {};
        const salaryInfo = {};
        
        for (const [key, value] of Object.entries(details)) {
            // Skip empty values
            if (value === null || value === undefined || value === '' || 
               (Array.isArray(value) && value.length === 0) || 
               (typeof value === 'object' && (!value || Object.keys(value).length === 0 || 
               (value.name === null && (!('overlap' in value) || value.overlap === null))))) {
                continue;
            }
            
            // Sort into appropriate section
            if (['title', 'description', 'discipline', 'jobType', 'seniority'].includes(key)) {
                basicInfo[key] = value;
            } else if (['availability', 'weeklyHours', 'estimatedWeeks', 'type'].includes(key)) {
                contractInfo[key] = value;
            } else if (['country', 'city', 'continents', 'countries', 'regions', 'timeZone'].includes(key)) {
                locationInfo[key] = value;
            } else if (['skills', 'languages'].includes(key)) {
                skillsInfo[key] = value;
            } else if (key.includes('Salary') || key.includes('HourlyRate')) {
                salaryInfo[key] = value;
            }
        }
        
        // Build HTML for sections
        let html = '';
        
        // Basic info section
        if (Object.keys(basicInfo).length > 0) {
            html += buildSection('Informations de Base', basicInfo);
        }
        
        // Skills section
        if (Object.keys(skillsInfo).length > 0) {
            html += buildSection('Compétences & Langues', skillsInfo);
        }
        
        // Contract section
        if (Object.keys(contractInfo).length > 0) {
            html += buildSection('Détails du Contrat', contractInfo);
        }
        
        // Location section
        if (Object.keys(locationInfo).length > 0) {
            html += buildSection('Localisation', locationInfo);
        }
        
        // Salary section
        if (Object.keys(salaryInfo).length > 0) {
            html += buildSection('Rémunération', salaryInfo);
        }
        
        if (html === '') {
            jobDetails.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"></rect><line x1="16" x2="16" y1="2" y2="6"></line><line x1="8" x2="8" y1="2" y2="6"></line><line x1="3" x2="21" y1="10" y2="10"></line><path d="m9 16 2 2 4-4"></path></svg>
                    </div>
                    <div class="empty-state-text">
                        Les détails de l'offre apparaîtront ici au fur et à mesure de votre conversation avec l'assistant.
                    </div>
                </div>
            `;
        } else {
            // If we have a title, show a nice summary card at the top
            if (basicInfo.title) {
                const jobType = basicInfo.jobType ? formatFieldValue('jobType', basicInfo.jobType) : '';
                const seniority = basicInfo.seniority ? formatFieldValue('seniority', basicInfo.seniority) : '';
                const location = locationInfo.city || (locationInfo.country && locationInfo.country.name) || '';
                
                const summaryHtml = `
                    <div class="job-summary">
                        <div class="job-summary-title">${basicInfo.title}</div>
                        ${seniority ? `
                            <div class="job-summary-detail">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="5"></circle><path d="M20 21a8 8 0 1 0-16 0"></path></svg>
                                ${seniority}
                            </div>
                        ` : ''}
                        ${jobType ? `
                            <div class="job-summary-detail">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"></path><circle cx="12" cy="12" r="4"></circle></svg>
                                ${jobType}
                            </div>
                        ` : ''}
                        ${location ? `
                            <div class="job-summary-detail">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"></path><circle cx="12" cy="10" r="3"></circle></svg>
                                ${typeof location === 'object' ? location.name : location}
                            </div>
                        ` : ''}
                    </div>
                `;
                
                html = summaryHtml + html;
            }
            
            jobDetails.innerHTML = html;
        }
    }
    
    function buildSection(title, fields) {
        let sectionHtml = `
            <div class="job-section">
                <h3 class="section-title">${title}</h3>
        `;
        
        for (const [key, value] of Object.entries(fields)) {
            sectionHtml += `
                <div class="job-field">
                    <div class="field-name">${formatFieldName(key)}</div>
                    <div class="field-value">${formatFieldValue(key, value)}</div>
                </div>
            `;
        }
        
        sectionHtml += `</div>`;
        return sectionHtml;
    }
    
    function formatFieldName(key) {
        // Convert camelCase to Title Case with spaces
        const formatted = key.replace(/([A-Z])/g, ' $1')
                            .replace(/^./, str => str.toUpperCase());
        
        // Special case handling
        const specialCases = {
            'Min Hourly Rate': 'Taux Horaire Min',
            'Max Hourly Rate': 'Taux Horaire Max',
            'Weekly Hours': 'Heures Hebdomadaires',
            'Estimated Weeks': 'Durée Estimée (semaines)',
            'Min Full Time Salary': 'Salaire Min (Temps Plein)',
            'Max Full Time Salary': 'Salaire Max (Temps Plein)',
            'Min Part Time Salary': 'Salaire Min (Temps Partiel)',
            'Max Part Time Salary': 'Salaire Max (Temps Partiel)',
            'Job Type': 'Type de Contrat',
            'Time Zone': 'Fuseau Horaire'
        };
        
        return specialCases[formatted] || formatted;
    }
    
    function formatFieldValue(key, value) {
        if (value === null || value === undefined) return '';
        
        if (typeof value === 'object') {
            if (Array.isArray(value)) {
                if (value.length === 0) return '';
                
                if (key === 'skills') {
                    return value.map(skill => {
                        return `<span class="tag ${skill.mandatory ? 'mandatory' : 'optional'}">${skill.name}</span>`;
                    }).join(' ');
                }
                
                if (key === 'languages') {
                    return value.map(lang => {
                        return `<span class="tag">${lang.name} (${lang.level})</span>`;
                    }).join(' ');
                }
                
                if (value[0] && value[0].name) {
                    return value.map(item => item.name).join(', ');
                }
                
                return JSON.stringify(value);
            } else {
                if (key === 'timeZone' && value.name) {
                    return `${value.name} (Chevauchement: ${value.overlap || 0}h)`;
                }
                
                if (value.name) {
                    return value.name;
                }
                
                return JSON.stringify(value);
            }
        }
        
        // Format numbers for salary and rates
        if (typeof value === 'number') {
            if (key.includes('Salary')) {
                return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(value);
            }
            
            if (key.includes('HourlyRate')) {
                return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(value) + '/h';
            }
            
            if (key === 'availability') {
                return value === 0 ? 'Immédiat' : `${value} semaine${value > 1 ? 's' : ''}`;
            }
        }
        
        // Format enum values
        if (key === 'jobType') {
            const jobTypes = {
                'FREELANCE': 'Freelance',
                'FULLTIME': 'Temps plein',
                'PARTTIME': 'Temps partiel'
            };
            return jobTypes[value] || value;
        }
        
        if (key === 'type') {
            const types = {
                'REMOTE': 'À distance',
                'ONSITE': 'Sur site',
                'HYBRID': 'Hybride'
            };
            return types[value] || value;
        }
        
        if (key === 'seniority') {
            const seniority = {
                'JUNIOR': 'Junior',
                'MID': 'Intermédiaire',
                'SENIOR': 'Senior'
            };
            return seniority[value] || value;
        }
        
        return value;
    }
    
    function formatJSONInMessage(message) {
        // Find JSON blocks in the message
        const jsonRegex = /({[\s\S]*?})/g;
        const matches = message.match(jsonRegex);
        
        if (!matches) return null;
        
        let formattedMessage = message;
        
        for (const match of matches) {
            try {
                // Try to parse as JSON
                const jsonObj = JSON.parse(match);
                const jsonFormatted = JSON.stringify(jsonObj, null, 2);
                const htmlFormatted = `<pre class="json-code">${jsonFormatted}</pre>`;
                formattedMessage = formattedMessage.replace(match, htmlFormatted);
            } catch (e) {
                // Not valid JSON, skip
                continue;
            }
        }
        
        return formattedMessage;
    }
    
    // Auto-resize textarea on input
    userInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
    
    // Make sure the textarea responds to focus
    userInput.addEventListener('focus', function() {
        document.querySelector('.input-wrapper').classList.add('focused');
    });
    
    userInput.addEventListener('blur', function() {
        document.querySelector('.input-wrapper').classList.remove('focused');
    });
});