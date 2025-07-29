document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const resultsContainer = document.getElementById('results');
    const resultsContent = document.getElementById('resultsContent');
    const loading = document.getElementById('loading');

    searchForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const companyName = document.getElementById('companyName').value.trim();
        const ceoChecked = document.getElementById('ceo').checked;
        const cfoChecked = document.getElementById('cfo').checked;
        const treasurerChecked = document.getElementById('treasurer').checked;

        if (!companyName) {
            alert('Please enter a company name');
            return;
        }

        if (!ceoChecked && !cfoChecked && !treasurerChecked) {
            alert('Please select at least one executive role to search');
            return;
        }

        // Show loading
        loading.style.display = 'block';
        resultsContainer.style.display = 'none';

        try {
            // Extract ticker from company name (you might want to implement a ticker lookup)
            const ticker = extractTickerFromCompanyName(companyName);
            
            if (!ticker) {
                throw new Error('Could not determine ticker symbol for this company. Please try with a more specific company name.');
            }

            const response = await fetch(`http://localhost:8000/company_info/${encodeURIComponent(companyName)}/${ticker}`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            displayResults(data, companyName);

        } catch (error) {
            console.error('Error:', error);
            displayError(error.message);
        } finally {
            loading.style.display = 'none';
        }
    });

    function extractTickerFromCompanyName(companyName) {
        // This is a simple mapping - in a real application, you'd want a more sophisticated approach
        const tickerMap = {
            'apple': 'AAPL',
            'microsoft': 'MSFT',
            'google': 'GOOGL',
            'amazon': 'AMZN',
            'tesla': 'TSLA',
            'netflix': 'NFLX',
            'meta': 'META',
            'nvidia': 'NVDA',
            'newmarket': 'NEU',
            'synnex': 'SNX',
            'ingredion': 'INGR',
            'bruker': 'BRKR'
        };

        const normalizedName = companyName.toLowerCase().replace(/[^a-z]/g, '');
        
        for (const [key, ticker] of Object.entries(tickerMap)) {
            if (normalizedName.includes(key)) {
                return ticker;
            }
        }

        // If no match found, try to extract from the company name
        const words = companyName.split(' ');
        if (words.length > 0) {
            // Take first word and convert to uppercase (simple approach)
            return words[0].toUpperCase().substring(0, 4);
        }

        return null;
    }

    function displayResults(data, companyName) {
        resultsContent.innerHTML = '';

        // Company Overview
        const overviewSection = document.createElement('div');
        overviewSection.className = 'result-section';
        overviewSection.innerHTML = `
            <h3>Company Overview</h3>
            <p><strong>Company:</strong> ${companyName}</p>
            <p><strong>Industry:</strong> ${data.industry || 'Not available'}</p>
            <p><strong>Industry Description:</strong> ${data.industry_blurb || 'Not available'}</p>
        `;
        resultsContent.appendChild(overviewSection);

        // Executives Section
        if (data.executives) {
            const executivesSection = document.createElement('div');
            executivesSection.className = 'result-section';
            executivesSection.innerHTML = `
                <h3>Executive Information</h3>
                ${data.executives.ceo ? `<p><strong>CEO:</strong> ${data.executives.ceo}</p>` : ''}
                ${data.executives.cfo ? `<p><strong>CFO:</strong> ${data.executives.cfo}</p>` : ''}
                ${data.executives.treasurer ? `<p><strong>Treasurer:</strong> ${data.executives.treasurer}</p>` : ''}
            `;
            resultsContent.appendChild(executivesSection);
        }

        // Email Information
        if (data.emails) {
            const emailsSection = document.createElement('div');
            emailsSection.className = 'result-section';
            emailsSection.innerHTML = `
                <h3>Email Information</h3>
                ${data.emails.cfo_email ? `<p><strong>CFO Email:</strong> ${data.emails.cfo_email}</p>` : ''}
                ${data.emails.treasurer_email ? `<p><strong>Treasurer Email:</strong> ${data.emails.treasurer_email}</p>` : ''}
                ${data.emails.domain ? `<p><strong>Email Domain:</strong> ${data.emails.domain}</p>` : ''}
                ${data.emails.format ? `<p><strong>Email Format:</strong> ${data.emails.format}</p>` : ''}
            `;
            resultsContent.appendChild(emailsSection);
        }

        // Debt and Liquidity Information
        if (data.debt_liquidity_summary && data.debt_liquidity_summary.length > 0) {
            const debtSection = document.createElement('div');
            debtSection.className = 'result-section';
            debtSection.innerHTML = `
                <h3>Debt and Liquidity Analysis</h3>
                <div class="debt-summary">
                    ${data.debt_liquidity_summary.map(item => {
                        if (item.startsWith('-')) {
                            return `<p style="margin-left: 20px; color: #666;">${item}</p>`;
                        } else if (item.startsWith('$')) {
                            return `<div class="debt-item"><strong>${item}</strong></div>`;
                        } else {
                            return `<p>${item}</p>`;
                        }
                    }).join('')}
                </div>
            `;
            resultsContent.appendChild(debtSection);
        }

        // 10-Q Link
        if (data.latest_10q_link) {
            const linkSection = document.createElement('div');
            linkSection.className = 'result-section';
            linkSection.innerHTML = `
                <h3>Latest 10-Q Filing</h3>
                <p><a href="${data.latest_10q_link}" target="_blank" style="color: #4299e1; text-decoration: none;">View Latest 10-Q Filing</a></p>
            `;
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
}); 