<#import "template.ftl" as layout>
<@layout.emailLayout>
  <h1 style="margin:0 0 16px 0; font-family:Georgia,'Times New Roman',serif;
             font-size:23px; font-weight:normal; color:#0B1020;">Confirm your email</h1>

  <p style="margin:0 0 4px 0;">Welcome to Freepod. Confirm this email address to
  finish setting up your account and start spinning up your private apps.</p>

  <@layout.button href=link label="Verify my email" />

  <p style="margin:0 0 16px 0; font-size:14px; color:#6B7488;">
  This link expires in ${linkExpirationFormatter(linkExpiration)}. If you didn't create
  a Freepod account, you can safely ignore this email.</p>

  <p style="margin:0; font-size:13px; color:#8A93A8;">
  If the button doesn't work, copy and paste this link into your browser:<br/>
  <a href="${link}" style="color:#2563EB; word-break:break-all;">${link}</a></p>
</@layout.emailLayout>
