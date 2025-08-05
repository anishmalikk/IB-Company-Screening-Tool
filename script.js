document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const resultsContainer = document.getElementById('results');
    const resultsContent = document.getElementById('resultsContent');
    const loading = document.getElementById('loading');

    searchForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const companyName = document.getElementById('companyName').value.trim();
        const tickerSymbol = document.getElementById('tickerSymbol').value.trim().toUpperCase();
        const includeExecutives = document.getElementById('include_executives').checked;
        const includeEmails = document.getElementById('include_emails').checked;
        const includeIndustry = document.getElementById('include_industry').checked;
        const includeIndustryBlurb = document.getElementById('include_industry_blurb').checked;
        const include10qLink = document.getElementById('include_10q_link').checked;
        const include10kLink = document.getElementById('include_10k_link').checked;
        const includeDebtLiquidity = document.getElementById('include_debt_liquidity').checked;

        if (!companyName) {
            alert('Please enter a company name');
            return;
        }

        if (!tickerSymbol) {
            alert('Please enter a ticker symbol');
            return;
        }

        if (!includeExecutives && !includeEmails && !includeIndustry && !includeIndustryBlurb && !include10qLink && !include10kLink && !includeDebtLiquidity) {
            alert('Please select at least one function to run');
            return;
        }

        // Show loading
        loading.style.display = 'block';
        resultsContainer.style.display = 'none';

        try {
            // Build query parameters
            const params = new URLSearchParams({
                include_executives: includeExecutives,
                include_emails: includeEmails,
                include_industry: includeIndustry,
                include_industry_blurb: includeIndustryBlurb,
                include_10q_link: include10qLink,
                include_10k_link: include10kLink,
                include_debt_liquidity: includeDebtLiquidity
            });

            const response = await fetch(`http://localhost:8000/company_info/${encodeURIComponent(companyName)}/${tickerSymbol}?${params}`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            displayResults(data, companyName, tickerSymbol);

        } catch (error) {
            console.error('Error:', error);
            displayError(error.message);
        } finally {
            loading.style.display = 'none';
        }
    });

    function displayResults(data, companyName, tickerSymbol) {
        resultsContent.innerHTML = '';

        // Validate data structure
        if (!data || typeof data !== 'object') {
            displayError('Invalid response data received from server');
            return;
        }

        // Company Overview
        const overviewSection = document.createElement('div');
        overviewSection.className = 'result-section';
        overviewSection.innerHTML = `
            <h3>Company Overview</h3>
            <p><strong>Company:</strong> ${companyName}</p>
            <p><strong>Ticker:</strong> ${tickerSymbol}</p>
            ${data.industry ? `<p><strong>Industry:</strong> ${data.industry}</p>` : ''}
            ${data.industry_blurb ? `<p><strong>Industry Description:</strong> ${data.industry_blurb}</p>` : ''}
        `;
        resultsContent.appendChild(overviewSection);

        // Executives Section
        if (data.executives && typeof data.executives === 'object') {
            const executivesSection = document.createElement('div');
            executivesSection.className = 'result-section';
            
            if (data.executives.error) {
                executivesSection.innerHTML = `
                    <h3>Executive Information</h3>
                    <p class="error-message">${data.executives.error}</p>
                `;
            } else {
                let executiveContent = '<h3>Executive Information</h3>';
                
                // Basic executive info
                if (data.executives.ceo && typeof data.executives.ceo === 'string') {
                    executiveContent += `<p><strong>CEO:</strong> ${data.executives.ceo}</p>`;
                }
                if (data.executives.cfo && typeof data.executives.cfo === 'string') {
                    executiveContent += `<p><strong>CFO:</strong> ${data.executives.cfo}</p>`;
                }
                if (data.executives.treasurer && typeof data.executives.treasurer === 'string') {
                    executiveContent += `<p><strong>Treasurer:</strong> ${data.executives.treasurer}</p>`;
                }
                
                // Enhanced treasurer metadata from intelligent system
                if (data.executives.treasurer_metadata && typeof data.executives.treasurer_metadata === 'object') {
                    const metadata = data.executives.treasurer_metadata;
                    
                    // Show possible treasurers if available
                    if (metadata.candidates && Array.isArray(metadata.candidates) && metadata.candidates.length > 0) {
                        executiveContent += '<p><strong>Possible Treasurers:</strong></p>';
                        executiveContent += '<ul style="padding-left: 20px; margin: 10px 0; word-wrap: break-word; overflow-wrap: break-word;">';
                        // Show all candidates without numbering
                        metadata.candidates.forEach((candidate) => {
                            if (typeof candidate === 'string') {
                                executiveContent += `<li style="margin-bottom: 5px; word-wrap: break-word; overflow-wrap: break-word;">${candidate}</li>`;
                            } else if (typeof candidate === 'object' && candidate.name) {
                                // Handle candidate objects with LinkedIn URLs
                                const linkedinLink = candidate.linkedin_url ? 
                                    ` - <a href="${candidate.linkedin_url}" target="_blank" style="color: #0077b5; text-decoration: none;">LinkedIn</a>` : '';
                                executiveContent += `<li style="margin-bottom: 5px; word-wrap: break-word; overflow-wrap: break-word;">${candidate.name}${linkedinLink}</li>`;
                            }
                        });
                        executiveContent += '</ul>';
                    }
                }
                
                executivesSection.innerHTML = executiveContent;
            }
            resultsContent.appendChild(executivesSection);
        }

        // Email Information
        if (data.emails && typeof data.emails === 'object') {
            const emailsSection = document.createElement('div');
            emailsSection.className = 'result-section';
            
            if (data.emails.error) {
                emailsSection.innerHTML = `
                    <h3>Email Information</h3>
                    <p class="error-message">${data.emails.error}</p>
                `;
            } else {
                let emailContent = '<h3>Email Information</h3>';
                
                if (data.emails.cfo_email && typeof data.emails.cfo_email === 'string') {
                    emailContent += `<p><strong>CFO Email:</strong> ${data.emails.cfo_email}</p>`;
                }
                
                // Enhanced treasurer email handling - only show if we have a treasurer email
                if (data.emails.treasurer_email && typeof data.emails.treasurer_email === 'string') {
                    emailContent += `<p><strong>Treasurer Email:</strong> ${data.emails.treasurer_email}</p>`;
                }
                
                if (data.emails.domain && typeof data.emails.domain === 'string') {
                    emailContent += `<p><strong>Email Domain:</strong> ${data.emails.domain}</p>`;
                }
                if (data.emails.format && typeof data.emails.format === 'string') {
                    emailContent += `<p><strong>Email Format:</strong> ${data.emails.format}</p>`;
                }
                

                
                // Legacy email detection info (fallback)
                if (data.emails.source_email && typeof data.emails.source_email === 'string') {
                    emailContent += `<p><strong>Source Email:</strong> ${data.emails.source_email}</p>`;
                }
                if (data.emails.source_name && typeof data.emails.source_name === 'string') {
                    emailContent += `<p><strong>Source Name:</strong> ${data.emails.source_name}</p>`;
                }
                if (data.emails.source && typeof data.emails.source === 'string') {
                    emailContent += `<p><strong>Detection Method:</strong> ${data.emails.source}</p>`;
                }
                
                // Website source information
                if (data.emails.website_source && typeof data.emails.website_source === 'string') {
                    emailContent += `<p><strong>Website Source:</strong> ${data.emails.website_source}</p>`;
                }
                
                // All discovered emails dropdown
                if (data.emails.all_discovered_emails && Array.isArray(data.emails.all_discovered_emails) && data.emails.all_discovered_emails.length > 0) {
                    emailContent += `
                        <div class="discovered-emails-section" style="margin-top: 15px;">
                            <button class="dropdown-toggle" onclick="toggleDiscoveredEmails(this)" style="
                                background: #f8f9fa;
                                border: 1px solid #dee2e6;
                                border-radius: 5px;
                                padding: 8px 12px;
                                cursor: pointer;
                                font-size: 14px;
                                color: #495057;
                                display: flex;
                                align-items: center;
                                gap: 8px;
                            ">
                                <i class="fas fa-chevron-down" style="transition: transform 0.2s;"></i>
                                <span>View All Discovered Emails (${data.emails.all_discovered_emails.length})</span>
                            </button>
                            <div class="discovered-emails-content" style="
                                display: none;
                                margin-top: 10px;
                                padding: 15px;
                                background: #f8f9fa;
                                border-radius: 5px;
                                border: 1px solid #dee2e6;
                            ">
                                <p style="margin: 0 0 10px 0; font-size: 14px; color: #6c757d;">
                                    <i class="fas fa-info-circle"></i> 
                                    All emails found during the search, ranked by source quality and relevance:
                                </p>
                                <div class="emails-list" style="max-height: 300px; overflow-y: auto;">
                    `;
                    
                    data.emails.all_discovered_emails.forEach((emailInfo, index) => {
                        const qualityColor = emailInfo.quality === 'high' ? '#28a745' : 
                                           emailInfo.quality === 'medium' ? '#ffc107' : 
                                           emailInfo.quality === 'low' ? '#dc3545' : '#6c757d';
                        
                        const qualityIcon = emailInfo.quality === 'high' ? 'fa-check-circle' : 
                                          emailInfo.quality === 'medium' ? 'fa-exclamation-circle' : 
                                          emailInfo.quality === 'low' ? 'fa-times-circle' : 'fa-question-circle';
                        
                        const isSelected = emailInfo.email === data.emails.source_email;
                        const selectedStyle = isSelected ? 'background: #e3f2fd; border-left: 3px solid #2196f3;' : '';
                        
                        emailContent += `
                            <div class="email-item" style="
                                padding: 8px 12px;
                                margin: 4px 0;
                                border-radius: 4px;
                                border: 1px solid #dee2e6;
                                ${selectedStyle}
                            ">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div style="flex: 1;">
                                        <span style="font-weight: 500; color: #495057;">${emailInfo.email}</span>
                                        ${isSelected ? '<span style="color: #2196f3; margin-left: 8px;"><i class="fas fa-star"></i> Selected</span>' : ''}
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="
                                            color: ${qualityColor};
                                            font-size: 12px;
                                            font-weight: 500;
                                            display: flex;
                                            align-items: center;
                                            gap: 4px;
                                        ">
                                            <i class="fas ${qualityIcon}"></i>
                                            ${emailInfo.quality}
                                        </span>
                                        <span style="
                                            background: #e9ecef;
                                            padding: 2px 6px;
                                            border-radius: 3px;
                                            font-size: 11px;
                                            color: #6c757d;
                                        ">Score: ${emailInfo.score}</span>
                                    </div>
                                </div>
                                <div style="margin-top: 4px; font-size: 12px; color: #6c757d;">
                                    <i class="fas fa-link"></i> Source: ${emailInfo.source}
                                </div>
                            </div>
                        `;
                    });
                    
                    emailContent += `
                                </div>
                            </div>
                        </div>
                    `;
                }
                
                // Fallback reason for legacy system
                if (data.emails.fallback_reason && typeof data.emails.fallback_reason === 'string') {
                    emailContent += `<div class="fallback-notice" style="background: #fef3c7; padding: 10px; border-radius: 5px; margin-top: 10px;">`;
                    emailContent += `<p><strong>Note:</strong> Used legacy email system. ${data.emails.fallback_reason}</p>`;
                    emailContent += `</div>`;
                }
                
                // If no emails were found, show a message
                if (!data.emails.cfo_email && !data.emails.treasurer_email) {
                    emailContent += `<p style="color: #666; font-style: italic;">No specific executive emails found. Domain and format information may still be available.</p>`;
                }
                
                emailsSection.innerHTML = emailContent;
            }
            resultsContent.appendChild(emailsSection);
        }

        // Debt and Liquidity Information
        if (data.debt_liquidity_summary) {
            const debtSection = document.createElement('div');
            debtSection.className = 'result-section';
            
            if (Array.isArray(data.debt_liquidity_summary) && data.debt_liquidity_summary.length > 0) {
                // Only show if we have a valid 10-Q link
                if (data.latest_10q_link && !data.latest_10q_link.startsWith('Error:')) {
                    // Create a better filename for display
                    const companyNameElement = document.getElementById('companyName');
                    const tickerElement = document.getElementById('tickerSymbol');
                    const companyName = companyNameElement ? companyNameElement.value : '';
                    const ticker = tickerElement ? tickerElement.value : '';
                    
                    let displayFilename10Q = '10-Q Filing.html';
                    if (companyName && companyName.trim()) {
                        const cleanCompanyName = companyName.replace(/ /g, "_").replace(/,/g, "").replace(/\./g, "").replace(/&/g, "and");
                        displayFilename10Q = `${cleanCompanyName}_latest_10Q.html`;
                    } else if (ticker && ticker.trim()) {
                        displayFilename10Q = `${ticker}_latest_10Q.html`;
                    }
                    
                    let displayFilename10K = '10-K Filing.html';
                    if (companyName && companyName.trim()) {
                        const cleanCompanyName = companyName.replace(/ /g, "_").replace(/,/g, "").replace(/\./g, "").replace(/&/g, "and");
                        displayFilename10K = `${cleanCompanyName}_latest_10K.html`;
                    } else if (ticker && ticker.trim()) {
                        displayFilename10K = `${ticker}_latest_10K.html`;
                    }
                    
                    let debtContent = `
                        <h3>Debt and Liquidity Analysis</h3>
                        <div class="pdf-file-container" data-url="${data.latest_10q_link}">
                            <div class="pdf-file-icon" onclick="download10Q('${data.latest_10q_link}')" style="cursor: pointer;">
                                <i class="fas fa-file-code"></i>
                                <span>${displayFilename10Q}</span>
                            </div>
                            <p class="pdf-instructions">
                                <i class="fas fa-info-circle"></i> 
                                Click the file icon above to download the 10-Q filing.
                            </p>
                        </div>
                    `;
                    
                    // Add 10-K download if available
                    if (data.latest_10k_link && !data.latest_10k_link.startsWith('Error:')) {
                        debtContent += `
                            <div class="pdf-file-container" data-url="${data.latest_10k_link}" style="margin-top: 15px;">
                                <div class="pdf-file-icon" onclick="download10K('${data.latest_10k_link}')" style="cursor: pointer;">
                                    <i class="fas fa-file-code"></i>
                                    <span>${displayFilename10K}</span>
                                </div>
                                <p class="pdf-instructions">
                                    <i class="fas fa-info-circle"></i> 
                                    Click the file icon above to download the 10-K filing.
                                </p>
                            </div>
                        `;
                    }
                    
                    // Add debt analysis prompt if available
                    if (data.debt_analysis_prompt && !data.debt_analysis_prompt.startsWith('Error:')) {
                        debtContent += `
                            <div class="prompt-container">
                                <h4>Debt Analysis Prompt</h4>
                                <p class="prompt-description">
                                    <i class="fas fa-info-circle"></i> 
                                    Copy this prompt and use it with GPT to analyze the company's debt structure:
                                </p>
                                <div class="prompt-text-container">
                                    <textarea id="debtPromptText" class="prompt-textarea" readonly>${data.debt_analysis_prompt}</textarea>
                                    <button class="copy-btn" onclick="copyDebtPrompt()">
                                        <i class="fas fa-copy"></i> Copy Prompt
                                    </button>
                                </div>
                            </div>
                        `;
                    } else if (data.debt_analysis_prompt && data.debt_analysis_prompt.startsWith('Error:')) {
                        debtContent += `
                            <div class="prompt-container">
                                <h4>Debt Analysis Prompt</h4>
                                <p class="error-message">${data.debt_analysis_prompt}</p>
                            </div>
                        `;
                    }
                    
                    debtSection.innerHTML = debtContent;
                } else {
                    debtSection.innerHTML = `
                        <h3>Debt and Liquidity Analysis</h3>
                        <p class="error-message">No 10-Q filing available for download.</p>
                    `;
                }
            } else if (typeof data.debt_liquidity_summary === 'string' && data.debt_liquidity_summary.startsWith('Error:')) {
                debtSection.innerHTML = `
                    <h3>Debt and Liquidity Analysis</h3>
                    <p class="error-message">${data.debt_liquidity_summary}</p>
                `;
            }
            resultsContent.appendChild(debtSection);
        }

        // 10-Q Link
        if (data.latest_10q_link) {
            const linkSection = document.createElement('div');
            linkSection.className = 'result-section';
            
            if (data.latest_10q_link.startsWith('Error:')) {
                linkSection.innerHTML = `
                    <h3>Latest 10-Q Filing</h3>
                    <p class="error-message">${data.latest_10q_link}</p>
                `;
            } else {
                linkSection.innerHTML = `
                    <h3>Latest 10-Q Filing</h3>
                    <div class="url-display">
                        <strong>URL:</strong>
                        <div class="url-code">${data.latest_10q_link}</div>
                    </div>
                    <div class="q10-actions">
                        <a href="${data.latest_10q_link}" target="_blank" class="btn btn-primary">
                            <i class="fas fa-external-link-alt"></i> Open in New Window
                        </a>
                    </div>
                `;
            }
            resultsContent.appendChild(linkSection);
        }

        // 10-K Link
        if (data.latest_10k_link) {
            const linkSection = document.createElement('div');
            linkSection.className = 'result-section';
            
            if (data.latest_10k_link.startsWith('Error:')) {
                linkSection.innerHTML = `
                    <h3>Latest 10-K Filing</h3>
                    <p class="error-message">${data.latest_10k_link}</p>
                `;
            } else {
                linkSection.innerHTML = `
                    <h3>Latest 10-K Filing</h3>
                    <div class="url-display">
                        <strong>URL:</strong>
                        <div class="url-code">${data.latest_10k_link}</div>
                    </div>
                    <div class="k10-actions">
                        <a href="${data.latest_10k_link}" target="_blank" class="btn btn-primary">
                            <i class="fas fa-external-link-alt"></i> Open in New Window
                        </a>
                    </div>
                `;
            }
            resultsContent.appendChild(linkSection);
        }


        resultsContainer.style.display = 'block';
    }

    function displayError(message) {
        resultsContent.innerHTML = `
            <div class="error-message">
                <strong>Error:</strong> ${message}
            </div>
        `;
        resultsContainer.style.display = 'block';
    }

    function formatDebtAnalysis(debtItems) {
        let formattedHtml = '';
        
        for (let i = 0; i < debtItems.length; i++) {
            const item = debtItems[i];
            
            // Skip empty items
            if (!item || item.trim() === '') continue;
            
            // Supporting details (start with -)
            if (item.startsWith('-')) {
                formattedHtml += `<p style="margin-left: 20px; color: #666;">${item}</p>`;
            }
            // Main debt facilities (start with $ and contain facility details)
            else if (item.startsWith('$') && (
                item.includes('@') || 
                item.includes('mat.') || 
                item.includes('Term Loan') ||
                item.includes('Revolving') ||
                item.includes('Senior Notes') ||
                item.includes('Credit Facility') ||
                item.includes('Bonds') ||
                item.includes('Notes') ||
                item.includes('Arrangement')
            )) {
                formattedHtml += `<div class="debt-item"><strong>${item}</strong></div>`;
            }
            // Section headers (bold text that doesn't start with $ or -)
            else if (item.startsWith('**') && item.endsWith('**')) {
                formattedHtml += `<p><strong>${item.replace(/\*\*/g, '')}</strong></p>`;
            }
            // Separator lines
            else if (item.includes('=')) {
                formattedHtml += `<hr style="margin: 15px 0; border: none; border-top: 1px solid #e2e8f0;">`;
            }
            // Regular text
            else {
                formattedHtml += `<p>${item}</p>`;
            }
        }
        
        return formattedHtml;
    }

    // Function to download 10-Q file
    window.download10Q = function(url) {
        // Show loading state - use a more specific selector
        const pdfIcon = document.querySelector('.pdf-file-container[data-url="' + url + '"] .pdf-file-icon');
        if (pdfIcon) {
            pdfIcon.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Downloading...</span>';
        }
        
        // Get ticker and company name from the current page
        const tickerElement = document.getElementById('tickerSymbol');
        const companyElement = document.getElementById('companyName');
        const ticker = tickerElement ? tickerElement.value : '';
        const companyName = companyElement ? companyElement.value : '';
        
        if (!ticker) {
            console.error('No ticker found');
            // Fallback: open in new tab
            window.open(url, '_blank');
            if (pdfIcon) {
                pdfIcon.innerHTML = '<i class="fas fa-file-code"></i><span>10-Q Filing.html</span>';
            }
            return;
        }
        
        // Use our backend endpoint to download the file
        const downloadUrl = `http://localhost:8000/download_10q/${ticker}?company_name=${encodeURIComponent(companyName)}`;
        
        fetch(downloadUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                // Generate filename on frontend side instead of relying on header
                const tickerElement = document.getElementById('tickerSymbol');
                const companyElement = document.getElementById('companyName');
                const ticker = tickerElement ? tickerElement.value : '';
                const companyName = companyElement ? companyElement.value : '';
                
                let filename = '10Q_filing.html';
                if (companyName && companyName.trim()) {
                    const cleanCompanyName = companyName.replace(/ /g, "_").replace(/,/g, "").replace(/\./g, "").replace(/&/g, "and");
                    filename = `${cleanCompanyName}_latest_10Q.html`;
                } else if (ticker && ticker.trim()) {
                    filename = `${ticker}_latest_10Q.html`;
                }
                
                console.log('Generated filename:', filename);
                
                return response.blob().then(blob => ({ blob, filename }));
            })
            .then(({ blob, filename }) => {
                // Create a download link with the blob
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = filename;
                
                // Trigger download
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                // Clean up the blob URL
                URL.revokeObjectURL(link.href);
                
                // Restore the PDF icon with the correct filename
                if (pdfIcon) {
                    const companyNameElement = document.getElementById('companyName');
                    const tickerElement = document.getElementById('tickerSymbol');
                    const companyName = companyNameElement ? companyNameElement.value : '';
                    const ticker = tickerElement ? tickerElement.value : '';
                    
                    let displayFilename = '10-Q Filing.html';
                    if (companyName && companyName.trim()) {
                        const cleanCompanyName = companyName.replace(/ /g, "_").replace(/,/g, "").replace(/\./g, "").replace(/&/g, "and");
                        displayFilename = `${cleanCompanyName}_latest_10Q.html`;
                    } else if (ticker && ticker.trim()) {
                        displayFilename = `${ticker}_latest_10Q.html`;
                    }
                    
                    pdfIcon.innerHTML = `<i class="fas fa-file-code"></i><span>${displayFilename}</span>`;
                }
            })
            .catch(error => {
                console.error('Download failed:', error);
                // Fallback: open in new tab
                window.open(url, '_blank');
                
                // Restore the PDF icon with the correct filename
                if (pdfIcon) {
                    const companyNameElement = document.getElementById('companyName');
                    const tickerElement = document.getElementById('tickerSymbol');
                    const companyName = companyNameElement ? companyNameElement.value : '';
                    const ticker = tickerElement ? tickerElement.value : '';
                    
                    let displayFilename = '10-Q Filing.html';
                    if (companyName && companyName.trim()) {
                        const cleanCompanyName = companyName.replace(/ /g, "_").replace(/,/g, "").replace(/\./g, "").replace(/&/g, "and");
                        displayFilename = `${cleanCompanyName}_latest_10Q.html`;
                    } else if (ticker && ticker.trim()) {
                        displayFilename = `${ticker}_latest_10Q.html`;
                    }
                    
                    pdfIcon.innerHTML = `<i class="fas fa-file-code"></i><span>${displayFilename}</span>`;
                }
            });
    };

    // Function to download 10-K file
    window.download10K = function(url) {
        // Show loading state - use a more specific selector
        const pdfIcon = document.querySelector('.pdf-file-container[data-url="' + url + '"] .pdf-file-icon');
        if (pdfIcon) {
            pdfIcon.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Downloading...</span>';
        }
        
        // Get ticker and company name from the current page
        const tickerElement = document.getElementById('tickerSymbol');
        const companyElement = document.getElementById('companyName');
        const ticker = tickerElement ? tickerElement.value : '';
        const companyName = companyElement ? companyElement.value : '';
        
        if (!ticker) {
            console.error('No ticker found');
            // Fallback: open in new tab
            window.open(url, '_blank');
            if (pdfIcon) {
                pdfIcon.innerHTML = '<i class="fas fa-file-code"></i><span>10-K Filing.html</span>';
            }
            return;
        }
        
        // Use our backend endpoint to download the file
        const downloadUrl = `http://localhost:8000/download_10k/${ticker}?company_name=${encodeURIComponent(companyName)}`;
        
        fetch(downloadUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                // Generate filename on frontend side instead of relying on header
                const tickerElement = document.getElementById('tickerSymbol');
                const companyElement = document.getElementById('companyName');
                const ticker = tickerElement ? tickerElement.value : '';
                const companyName = companyElement ? companyElement.value : '';
                
                let filename = '10K_filing.html';
                if (companyName && companyName.trim()) {
                    const cleanCompanyName = companyName.replace(/ /g, "_").replace(/,/g, "").replace(/\./g, "").replace(/&/g, "and");
                    filename = `${cleanCompanyName}_latest_10K.html`;
                } else if (ticker && ticker.trim()) {
                    filename = `${ticker}_latest_10K.html`;
                }
                
                console.log('Generated filename:', filename);
                
                return response.blob().then(blob => ({ blob, filename }));
            })
            .then(({ blob, filename }) => {
                // Create a download link with the blob
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = filename;
                
                // Trigger download
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                // Clean up the blob URL
                URL.revokeObjectURL(link.href);
                
                // Restore the PDF icon with the correct filename
                if (pdfIcon) {
                    const companyNameElement = document.getElementById('companyName');
                    const tickerElement = document.getElementById('tickerSymbol');
                    const companyName = companyNameElement ? companyNameElement.value : '';
                    const ticker = tickerElement ? tickerElement.value : '';
                    
                    let displayFilename = '10-K Filing.html';
                    if (companyName && companyName.trim()) {
                        const cleanCompanyName = companyName.replace(/ /g, "_").replace(/,/g, "").replace(/\./g, "").replace(/&/g, "and");
                        displayFilename = `${cleanCompanyName}_latest_10K.html`;
                    } else if (ticker && ticker.trim()) {
                        displayFilename = `${ticker}_latest_10K.html`;
                    }
                    
                    pdfIcon.innerHTML = `<i class="fas fa-file-code"></i><span>${displayFilename}</span>`;
                }
            })
            .catch(error => {
                console.error('Download failed:', error);
                // Fallback: open in new tab
                window.open(url, '_blank');
                
                // Restore the PDF icon with the correct filename
                if (pdfIcon) {
                    const companyNameElement = document.getElementById('companyName');
                    const tickerElement = document.getElementById('tickerSymbol');
                    const companyName = companyNameElement ? companyNameElement.value : '';
                    const ticker = tickerElement ? tickerElement.value : '';
                    
                    let displayFilename = '10-K Filing.html';
                    if (companyName && companyName.trim()) {
                        const cleanCompanyName = companyName.replace(/ /g, "_").replace(/,/g, "").replace(/\./g, "").replace(/&/g, "and");
                        displayFilename = `${cleanCompanyName}_latest_10K.html`;
                    } else if (ticker && ticker.trim()) {
                        displayFilename = `${ticker}_latest_10K.html`;
                    }
                    
                    pdfIcon.innerHTML = `<i class="fas fa-file-code"></i><span>${displayFilename}</span>`;
                }
            });
    };

    // Function to copy debt analysis prompt
    window.copyDebtPrompt = function() {
        const textarea = document.getElementById('debtPromptText');
        if (textarea) {
            textarea.select();
            textarea.setSelectionRange(0, 99999); // For mobile devices
            
            try {
                document.execCommand('copy');
                
                // Show success feedback
                const copyBtn = document.querySelector('.copy-btn');
                if (copyBtn) {
                    const originalText = copyBtn.innerHTML;
                    copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                    copyBtn.style.background = '#48bb78';
                    
                    setTimeout(() => {
                        copyBtn.innerHTML = originalText;
                        copyBtn.style.background = '';
                    }, 2000);
                }
            } catch (err) {
                console.error('Failed to copy: ', err);
                alert('Failed to copy prompt. Please select and copy manually.');
            }
        }
    };

    // Function to handle drag and drop of PDF file
    window.drag = function(event) {
        const container = event.target.closest('.pdf-file-container');
        const url = container.dataset.url || '';
        
        if (url) {
            // Set the URL as downloadable data
            event.dataTransfer.setData('text/uri-list', url);
            event.dataTransfer.setData('text/plain', url);
            
            // Create a download link
            const link = document.createElement('a');
            link.href = url;
            link.download = '10Q_filing.html';
            
            // Try to get filename from URL
            const urlParts = url.split('/');
            if (urlParts.length > 0) {
                const filename = urlParts[urlParts.length - 1];
                if (filename && filename.includes('.')) {
                    link.download = filename;
                }
            }
            
            // Add the link to data transfer
            event.dataTransfer.setData('text/html', link.outerHTML);
            event.dataTransfer.effectAllowed = 'copy';
        }
    };

    // Function to toggle discovered emails dropdown
    window.toggleDiscoveredEmails = function(button) {
        const content = button.nextElementSibling;
        const icon = button.querySelector('i.fas');
        
        if (content.style.display === 'none') {
            content.style.display = 'block';
            icon.style.transform = 'rotate(180deg)';
        } else {
            content.style.display = 'none';
            icon.style.transform = 'rotate(0deg)';
        }
    };
}); 