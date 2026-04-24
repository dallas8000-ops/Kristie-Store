# East Africa Ecommerce Platform

A professional ecommerce platform for East Africa, focused on women’s clothing, accessories, jewelry, shoes, rings, perfume, and lingerie. Built with Django (backend), React + Bootstrap (frontend), and Node.js microservices for payment integrations (WorldRemit, Daraja, Flutterwave, etc.).

## Capstone Alignment
This project is being developed as a full-stack capstone application and is aligned to the following core capstone expectations:
- Functional full-stack application with working backend and frontend flows
- Attractive, responsive interface across key shopping pages
- Real-world inventory management through protected admin tools
- Clear project documentation, page mapping, and tech stack rationale

Current capstone fit:
- Operational: catalog, inventory, cart, admin-backed product management, and currency-aware shopping flows are implemented
- Aesthetically pleasing: branded home, about, catalog, inventory, and cart pages are in place
- Responsive design: major user-facing pages are responsive, with final QA still recommended across devices
- Recommended extras in progress: payment-provider flow and final QA still need completion for a stronger final capstone submission

## Project Description
East Africa Ecommerce Platform is a fashion-focused ecommerce experience designed for women-led commerce and modern retail across East Africa. The application combines a Django backend, database-managed inventory, and customer-facing shopping pages with dynamic currency conversion, cart management, catalog browsing, and protected admin editing. The goal is to provide a scalable marketplace foundation that can support premium fashion listings, mobile-first browsing, and region-aware payment expansion.

## Industry Context And Target Audience
- Industry: Fashion ecommerce / digital retail marketplace
- Primary audience: Women shoppers, boutique owners, and small fashion businesses across East Africa
- Secondary audience: Fashion entrepreneurs who need a manageable storefront and inventory workflow

## Elevator Pitch
East Africa Ecommerce Platform is a full-stack fashion marketplace built to help modern retailers showcase curated clothing collections, manage products securely through Django admin, and serve customers with responsive catalog browsing, real-time currency conversion, and scalable payment-ready checkout flows.

## Page And Feature Map
- Home: brand presentation, service summary, social/contact access, theme controls
- About: brand ethos, mission, vision, story, imagery, contact details
- Catalog: product cards, linked product images, modal detail view, admin-managed item visibility
- Inventory: product listing, size selection, quantity, purchase currency selector, payment method selector, add-to-cart flow
- Cart: order table, quantity updates, delete actions, converted totals, payment method summary
- Admin: secure editing for categories, products, product images, carts, and cart items

## Structure
- `backend/` — Django REST API (product, cart, user, and inventory management)
- `frontend/` — React + Bootstrap UI (modern, responsive, and mobile-friendly)
- `payments/` — Node.js microservices for African payment integrations
- `images/` — Product images and media

## Tech Stack
- Backend: Django, Django REST Framework, SQLite
- Frontend UI: Django templates for the current shopping flow, React + Vite workspace for frontend expansion
- Styling: Bootstrap 5 plus custom CSS
- Payments: Node.js + Express microservice stubs for WorldRemit, Daraja, Flutterwave, Airtel, and MTN expansion
- Media/Data: SQLite database with admin-managed products and linked product images
- Tooling: VS Code, GitHub Copilot, npm, Python virtual environment

## Features
- Modern, mobile-friendly UI/UX
- Home, About, Inventory, Cart pages
- Prominent Bootstrap navbar linking all pages
- Dynamic inventory and cart management
- Checkout order capture with country-aware payment instructions and order reference tracking
- Shopper authentication (signup/login/logout) with account-aware cart merge
- Contact inquiry workflow with admin persistence and real email notification support
- Payment method selection and provider-ready scaffolding (MTN, Airtel, WorldRemit)
- Designed for the East African market
- Storefront-first landing page for capstone demo presentation

## Live Demo
- Deployed URL: https://e-commerce-9kru.onrender.com
- Admin panel: https://e-commerce-9kru.onrender.com/admin/login/
- Default credentials: create a superuser on first deploy via `python manage.py createsuperuser`

## Architecture Decision — Django Templates vs React Frontend
This project uses a **dual-frontend approach** intentionally:

- **Django-rendered templates** (`backend/core/templates/`) are the live storefront — they handle the complete shopping flow (catalog, inventory, cart, auth, contact) with server-side rendering, CSRF protection, and session management built in. This approach was chosen for rapid, secure delivery with zero JavaScript build step for the critical customer path.

- **React + Vite** (`frontend/`) is a separate workspace scaffolded for future expansion — progressive migration of individual pages as the team grows and API endpoints mature. DRF endpoints (`/api/products/`, `/api/categories/`) are already in place to support this.

This pattern is common in production Django shops doing a gradual SSR-to-SPA migration. In interviews, the key point is: the Django-rendered storefront is fully functional today; React is the planned successor for individual high-interactivity pages.

## Capstone Deliverables Checklist
- Codebase: present in this repository
- Project documentation: partially complete in this README and should continue to be expanded
- Planning document and Trello-ready task breakdown: see `PROJECT_PLANNING.md`
- GitHub repository link: add the final public/private repo link here before submission
- Trello board link: https://trello.com/b/s8Rpm9in/kristie-store
- Industry context and target audience: documented above
- Elevator pitch: documented above
- List of pages and features: documented above
- Tech stack explanation: documented above

## Remaining Work To Fully Strengthen Capstone Submission
1. Wire one payment provider sandbox end-to-end
- WorldRemit confirmation workflow is the recommended next step (config scaffolding already in place)

2. Final responsive QA
- Verify mobile/tablet behavior for inventory, cart, catalog modal, and admin sign-in path

3. Add project management references
- Insert GitHub repo link before submission

## Recently Completed Milestones
- Shopper authentication implemented: signup/login/logout routes plus account-aware cart merge
- Communication feature implemented: contact inquiries save in admin and send real SMTP email notifications
- Storefront landing update completed: portfolio-style home replaced by ecommerce-first hero and conversion-focused sections

## Environment Setup (Backend)
1. Go to the backend folder:
	- `cd backend`
2. Create your local environment file from the template:
	- Copy `.env.example` to `.env`
3. Set a strong Django secret key in `.env`:
	- `DJANGO_SECRET_KEY=your-strong-secret-key`

Notes:
- `.env` is local-only and ignored by git.
- `.env.example` is safe to commit and share.

## Local Run Guide
1. Backend API (Django)
	- `cd backend`
	- `c:/Ecommerce/env/Scripts/python.exe manage.py migrate`
	- `c:/Ecommerce/env/Scripts/python.exe manage.py load_sample_inventory`
	- `c:/Ecommerce/env/Scripts/python.exe manage.py runserver`

2. Link uploaded catalog images to products
	- Put product images in `images/` at the workspace root.
	- Use filenames that match product names (for example, `Classic Blouse.jpg`).
	- Run: `cd backend`
	- Run: `c:/Ecommerce/env/Scripts/python.exe manage.py link_static_images_to_products`

3. Frontend (React + Vite)
	- `cd frontend`
	- `npm install`
	- `npm run dev`
	- App runs on `http://localhost:5173`

4. Payments service (Node.js)
	- `cd payments`
	- `npm install`
	- `npm run dev`
	- Service runs on `http://localhost:5000`

## Admin Access (Secure Inventory Management)
1. Create an admin account (superuser):
	- `cd backend`
	- `c:/Ecommerce/env/Scripts/python.exe manage.py createsuperuser`
2. Open Django admin sign-in:
	- `http://127.0.0.1:8000/admin/login/`
3. Manage inventory safely in Django Admin:
	- Categories
	- Products
	- Product images (inline on product)
	- Carts and cart items

Tip:
- Use the `Admin Sign In` button in the top navigation to access the admin login quickly.

---

Add your images to the `images/` folder. See project files for further instructions.

---

## About the Developer

**Barney R. Gilliom**  
Founder & Lead Developer, East Africa Ecommerce Platform  
Full-Stack Developer | JavaScript · React · Node.js · Python · Django · SQL · MongoDB  
Wimauma, FL  •  682-460-4048  •  dallas8000@gmail.com  
[LinkedIn](https://www.linkedin.com/in/barney-gilliom-959981337) • [GitHub](https://github.com/dallas8000-ops) • [Portfolio](https://jnalumansi.onrender.com)

**Mission & Founding Statement:**  
The East Africa Ecommerce Platform was founded to empower women entrepreneurs and small businesses across East Africa by providing a modern, secure, and scalable online marketplace. Our mission is to make high-quality fashion, accessories, and lifestyle products accessible to all, while supporting local talent and economic growth through technology.

Barney is a passionate Full-Stack Developer and the creator of this platform. He specializes in building robust, user-focused web applications using Django, React, Node.js, and cloud technologies. With 3+ years of independent consulting and 25+ years of professional experience, Barney is committed to delivering secure, scalable, and impactful solutions for the African market. He believes in technology as a force for economic empowerment and social good.

**Contact:**  
For project, partnership, or business inquiries, please contact Barney directly at:

- Email: dallas8000@gmail.com
- Phone: 682-460-4048
- [LinkedIn](https://www.linkedin.com/in/barney-gilliom-959981337)

> **Note:** This About Me section is for developer introduction only and does not represent the business or brand identity of the ecommerce platform. For project or business inquiries, please use the contact information above.