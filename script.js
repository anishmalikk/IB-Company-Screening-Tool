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
        const includeDebtLiquidity = document.getElementById('include_debt_liquidity').checked;

        if (!companyName) {
            alert('Please enter a company name');
            return;
        }

        if (!tickerSymbol) {
            alert('Please enter a ticker symbol');
            return;
        }

        if (!includeExecutives && !includeEmails && !includeIndustry && !includeIndustryBlurb && !include10qLink && !includeDebtLiquidity) {
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
        if (data.executives) {
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
                if (data.executives.ceo) {
                    executiveContent += `<p><strong>CEO:</strong> ${data.executives.ceo}</p>`;
                }
                if (data.executives.cfo) {
                    executiveContent += `<p><strong>CFO:</strong> ${data.executives.cfo}</p>`;
                }
                if (data.executives.treasurer) {
                    executiveContent += `<p><strong>Treasurer:</strong> ${data.executives.treasurer}</p>`;
                }
                
                // Enhanced treasurer metadata from intelligent system
                if (data.executives.treasurer_metadata) {
                    const metadata = data.executives.treasurer_metadata;
                    
                    executiveContent += '<div class="treasurer-metadata">';
                    executiveContent += '<h4>Treasurer Detection Details</h4>';
                    
                    // Confidence indicator
                    const confidenceColor = metadata.confidence === 'high' ? '#10b981' : 
                                          metadata.confidence === 'medium' ? '#f59e0b' : '#ef4444';
                    executiveContent += `<p><strong>Confidence:</strong> <span style="color: ${confidenceColor}; font-weight: bold;">${metadata.confidence}</span></p>`;
                    
                    // Status
                    executiveContent += `<p><strong>Detection Status:</strong> ${metadata.status.replace(/_/g, ' ')}</p>`;
                    
                    // Email strategy
                    executiveContent += `<p><strong>Email Strategy:</strong> ${metadata.email_strategy.replace(/_/g, ' ')}</p>`;
                    
                    // Recommendation
                    if (metadata.recommendation) {
                        executiveContent += `<p><strong>System Recommendation:</strong> <em>${metadata.recommendation}</em></p>`;
                    }
                    
                    // Multiple candidates
                    if (metadata.candidates && metadata.candidates.length > 0) {
                        executiveContent += '<p><strong>All Candidates Found:</strong></p>';
                        executiveContent += '<ul>';
                        metadata.candidates.forEach(candidate => {
                            executiveContent += `<li>${candidate}</li>`;
                        });
                        executiveContent += '</ul>';
                    }
                    
                    executiveContent += '</div>';
                }
                
                executivesSection.innerHTML = executiveContent;
            }
            resultsContent.appendChild(executivesSection);
        }

        // Email Information
        if (data.emails) {
            const emailsSection = document.createElement('div');
            emailsSection.className = 'result-section';
            
            if (data.emails.error) {
                emailsSection.innerHTML = `
                    <h3>Email Information</h3>
                    <p class="error-message">${data.emails.error}</p>
                `;
            } else {
                let emailContent = '<h3>Email Information</h3>';
                
                if (data.emails.cfo_email) {
                    emailContent += `<p><strong>CFO Email:</strong> ${data.emails.cfo_email}</p>`;
                }
                
                // Enhanced treasurer email handling
                if (data.emails.treasurer_email) {
                    emailContent += `<p><strong>Treasurer Email:</strong> ${data.emails.treasurer_email}</p>`;
                } else if (data.emails.treasurer_status) {
                    const statusColor = data.emails.treasurer_status === 'provided' ? '#10b981' : 
                                      data.emails.treasurer_status === 'skipped_due_to_uncertainty' ? '#f59e0b' : '#6b7280';
                    emailContent += `<p><strong>Treasurer Email:</strong> <span style="color: ${statusColor};">${data.emails.treasurer_status.replace(/_/g, ' ')}</span></p>`;
                }
                
                if (data.emails.domain) {
                    emailContent += `<p><strong>Email Domain:</strong> ${data.emails.domain}</p>`;
                }
                if (data.emails.format) {
                    emailContent += `<p><strong>Email Format:</strong> ${data.emails.format}</p>`;
                }
                
                // Intelligent system email metadata
                if (data.emails.strategy_used) {
                    emailContent += `<p><strong>Strategy Used:</strong> ${data.emails.strategy_used.replace(/_/g, ' ')}</p>`;
                }
                
                if (data.emails.uncertainty_reason) {
                    emailContent += '<div class="email-uncertainty">';
                    emailContent += `<p><strong>Why no treasurer email:</strong> <em>${data.emails.uncertainty_reason}</em></p>`;
                    emailContent += '</div>';
                }
                
                // Legacy email detection info (fallback)
                if (data.emails.source_email) {
                    emailContent += `<p><strong>Source Email:</strong> ${data.emails.source_email}</p>`;
                }
                if (data.emails.source_name) {
                    emailContent += `<p><strong>Source Name:</strong> ${data.emails.source_name}</p>`;
                }
                if (data.emails.source) {
                    emailContent += `<p><strong>Detection Method:</strong> ${data.emails.source}</p>`;
                }
                

                
                // Fallback reason for legacy system
                if (data.emails.fallback_reason) {
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
                    const companyName = document.getElementById('companyName') ? document.getElementById('companyName').value : '';
                    const ticker = document.getElementById('tickerSymbol') ? document.getElementById('tickerSymbol').value : '';
                    
                    let displayFilename = '10-Q Filing.pdf';
                    if (companyName) {
                        const cleanCompanyName = companyName.replace(" ", "_").replace(",", "").replace(".", "").replace("&", "and");
                        displayFilename = `${cleanCompanyName}_latest_10Q.pdf`;
                    } else if (ticker) {
                        displayFilename = `${ticker}_latest_10Q.pdf`;
                    }
                    
                    let debtContent = `
                        <h3>Debt and Liquidity Analysis</h3>
                        <div class="pdf-file-container" data-url="${data.latest_10q_link}">
                            <div class="pdf-file-icon" onclick="download10Q('${data.latest_10q_link}')" style="cursor: pointer;">
                                <i class="fas fa-file-pdf"></i>
                                <span>${displayFilename}</span>
                            </div>
                            <p class="pdf-instructions">
                                <i class="fas fa-info-circle"></i> 
                                Click the file icon above to download the 10-Q filing.
                            </p>
                        </div>
                    `;
                    
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
        // Show loading state
        const pdfIcon = document.querySelector('.pdf-file-icon');
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
                pdfIcon.innerHTML = '<i class="fas fa-file-pdf"></i><span>10-Q Filing.pdf</span>';
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
                if (companyName) {
                    const cleanCompanyName = companyName.replace(" ", "_").replace(",", "").replace(".", "").replace("&", "and");
                    filename = `${cleanCompanyName}_latest_10Q.html`;
                } else if (ticker) {
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
                    const companyName = document.getElementById('companyName') ? document.getElementById('companyName').value : '';
                    const ticker = document.getElementById('tickerSymbol') ? document.getElementById('tickerSymbol').value : '';
                    
                    let displayFilename = '10-Q Filing.pdf';
                    if (companyName) {
                        const cleanCompanyName = companyName.replace(" ", "_").replace(",", "").replace(".", "").replace("&", "and");
                        displayFilename = `${cleanCompanyName}_latest_10Q.pdf`;
                    } else if (ticker) {
                        displayFilename = `${ticker}_latest_10Q.pdf`;
                    }
                    
                    pdfIcon.innerHTML = `<i class="fas fa-file-pdf"></i><span>${displayFilename}</span>`;
                }
            })
            .catch(error => {
                console.error('Download failed:', error);
                // Fallback: open in new tab
                window.open(url, '_blank');
                
                // Restore the PDF icon with the correct filename
                if (pdfIcon) {
                    const companyName = document.getElementById('companyName') ? document.getElementById('companyName').value : '';
                    const ticker = document.getElementById('tickerSymbol') ? document.getElementById('tickerSymbol').value : '';
                    
                    let displayFilename = '10-Q Filing.pdf';
                    if (companyName) {
                        const cleanCompanyName = companyName.replace(" ", "_").replace(",", "").replace(".", "").replace("&", "and");
                        displayFilename = `${cleanCompanyName}_latest_10Q.pdf`;
                    } else if (ticker) {
                        displayFilename = `${ticker}_latest_10Q.pdf`;
                    }
                    
                    pdfIcon.innerHTML = `<i class="fas fa-file-pdf"></i><span>${displayFilename}</span>`;
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
}); 