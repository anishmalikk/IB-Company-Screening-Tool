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
                executivesSection.innerHTML = `
                    <h3>Executive Information</h3>
                    ${data.executives.ceo ? `<p><strong>CEO:</strong> ${data.executives.ceo}</p>` : ''}
                    ${data.executives.cfo ? `<p><strong>CFO:</strong> ${data.executives.cfo}</p>` : ''}
                    ${data.executives.treasurer ? `<p><strong>Treasurer:</strong> ${data.executives.treasurer}</p>` : ''}
                `;
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
                if (data.emails.treasurer_email) {
                    emailContent += `<p><strong>Treasurer Email:</strong> ${data.emails.treasurer_email}</p>`;
                }
                if (data.emails.domain) {
                    emailContent += `<p><strong>Email Domain:</strong> ${data.emails.domain}</p>`;
                }
                if (data.emails.format) {
                    emailContent += `<p><strong>Email Format:</strong> ${data.emails.format}</p>`;
                }
                if (data.emails.source_email) {
                    emailContent += `<p><strong>Source Email:</strong> ${data.emails.source_email}</p>`;
                }
                if (data.emails.source_name) {
                    emailContent += `<p><strong>Source Name:</strong> ${data.emails.source_name}</p>`;
                }
                if (data.emails.source) {
                    emailContent += `<p><strong>Detection Method:</strong> ${data.emails.source}</p>`;
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
                debtSection.innerHTML = `
                    <h3>Debt and Liquidity Analysis</h3>
                    <div class="debt-summary">
                        ${formatDebtAnalysis(data.debt_liquidity_summary)}
                    </div>
                `;
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
                    <p><a href="${data.latest_10q_link}" target="_blank" style="color: #4299e1; text-decoration: none;">View Latest 10-Q Filing</a></p>
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
}); 